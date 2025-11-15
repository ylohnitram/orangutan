#!/usr/bin/env python3
"""Interactive CLI that routes user prompts through the orangutan orchestrator."""

from __future__ import annotations

import argparse
import signal
import threading
import time
from typing import Any, Dict, List, Optional

from orchestrator import (PIPELINE_V01, Agent, execute_single_agent,
                          initialize_state, load_all_agents)


class OrangutanConsole:
    """Minimal interactive shell for routing tasks through the orchestrator."""

    def __init__(
        self,
        *,
        agents_dir: str,
        workflow_rules: str,
        use_mock_clis: bool,
        max_retries: int,
    ) -> None:
        self.agents_dir = agents_dir
        self.workflow_rules = workflow_rules
        self.use_mock_clis = use_mock_clis
        self.max_retries = max_retries
        self.agents: Dict[str, Agent] = load_all_agents(self.agents_dir)
        self.cancel_event = threading.Event()
        self.shutdown_event = threading.Event()
        self._process_lock = threading.Lock()
        self._current_process = None
        self._last_interrupt = 0.0
        signal.signal(signal.SIGINT, self._handle_sigint)

    # ------------------------------------------------------------------
    # Signal + cancellation helpers
    # ------------------------------------------------------------------

    def _handle_sigint(self, signum, frame) -> None:  # noqa: ARG002 (signal)
        now = time.time()
        if now - self._last_interrupt < 1.5:
            print("\n[orangutan] Force termination requested. Exiting…")
            self.force_terminate()
            raise SystemExit(1)

        self._last_interrupt = now
        print("\n[orangutan] Cancel requested. Press Ctrl+C again to exit immediately.")
        self.request_cancel()

    def request_cancel(self) -> None:
        self.cancel_event.set()
        self._terminate_current_process()

    def force_terminate(self) -> None:
        self.cancel_event.set()
        self.shutdown_event.set()
        self._terminate_current_process()

    def _track_process(self, proc) -> None:
        with self._process_lock:
            self._current_process = proc

    def _terminate_current_process(self) -> None:
        with self._process_lock:
            if self._current_process and self._current_process.poll() is None:
                self._current_process.terminate()

    # ------------------------------------------------------------------
    # User interaction
    # ------------------------------------------------------------------

    def run(self) -> int:
        self._render_welcome()
        while not self.shutdown_event.is_set():
            try:
                user_input = input("orangutan> ").strip()
            except EOFError:
                print()
                break
            if not user_input:
                continue
            if user_input.lower() in {":q", "quit", "exit"}:
                break
            if user_input.lower() in {":help", "help"}:
                self._render_help()
                continue
            self._dispatch_task(user_input)

        self.force_terminate()
        return 0

    def run_single_task(self, task: str) -> int:
        self._render_welcome(single_run=True)
        self._dispatch_task(task)
        self.force_terminate()
        return 0

    def _render_welcome(self, single_run: bool = False) -> None:
        mode = "mock" if self.use_mock_clis else "real"
        print("Orangutan interactive CLI")
        print(f"  Mode: {mode} CLIs | Agents: {', '.join(PIPELINE_V01)}")
        if not single_run:
            print("  Commands: :help, :q, quit, exit")

    def _render_help(self) -> None:
        print(
            "Commands:\n"
            "  <text>    Submit a natural-language request for the orchestrator\n"
            "  :help     Show this message\n"
            "  :q/quit   Exit the console\n"
            "Shortcuts:\n"
            "  Ctrl+C    Cancel the current run (press twice quickly to exit)"
        )

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    def _dispatch_task(self, task: str) -> None:
        task = task.strip()
        if not task:
            return
        self.cancel_event.clear()
        print(f"\n[orangutan] Dispatching: {task}")
        success = self._run_with_retries(task)
        if success:
            print("[orangutan] ✅ Task completed successfully.\n")
        else:
            if self.cancel_event.is_set():
                print("[orangutan] ⚠️  Task cancelled.\n")
            else:
                print("[orangutan] ❌ Task failed after retries.\n")
        self.cancel_event.clear()

    def _run_with_retries(self, task: str) -> bool:
        for attempt in range(1, self.max_retries + 1):
            if self.shutdown_event.is_set() or self.cancel_event.is_set():
                return False
            print(f"[orangutan] Attempt {attempt}/{self.max_retries}")
            state = initialize_state(task, self.workflow_rules)
            attempt_failed = not self._run_pipeline_once(task, state)
            if not attempt_failed:
                return True
            if attempt < self.max_retries and not self.cancel_event.is_set():
                print("[orangutan] Retrying task…")
        return False

    def _run_pipeline_once(self, task: str, state: Dict[str, Any]) -> bool:
        success = True
        for name in PIPELINE_V01:
            agent = self.agents.get(name)
            if not agent:
                print(f"[orangutan] Missing agent '{name}', skipping.")
                success = False
                continue
            if self.cancel_event.is_set() or self.shutdown_event.is_set():
                return False
            agent_success = self._run_agent(agent, state, task)
            if not agent_success:
                success = False
                break
        return success

    def _run_agent(self, agent: Agent, state: Dict[str, Any], task: str) -> bool:
        label = f"[{agent.name}] working"
        stop_event = threading.Event()
        spinner = threading.Thread(
            target=self._spinner,
            args=(label, stop_event),
            daemon=True,
        )
        spinner.start()
        agent_success, stdout, stderr = execute_single_agent(
            agent,
            state,
            task,
            use_mock_clis=self.use_mock_clis,
            verbose=False,
            on_process_start=self._track_process,
        )
        stop_event.set()
        spinner.join()

        summary_lines = self._summarize_output(stdout)
        icon = "✅" if agent_success else "❌"
        print(f"{icon} {agent.name}")
        for line in summary_lines:
            print(f"    {line}")
        if not agent_success and stderr:
            err_line = next(
                (line for line in stderr.splitlines() if line.strip()),
                "Unknown error",
            )
            print(f"    error: {err_line}")
        return agent_success

    @staticmethod
    def _summarize_output(stdout: str) -> List[str]:
        lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
        return lines[:3] or ["<no output>"]

    @staticmethod
    def _spinner(label: str, stop_event: threading.Event) -> None:
        frames = ["|", "/", "-", "\\"]
        idx = 0
        while not stop_event.is_set():
            frame = frames[idx % len(frames)]
            idx += 1
            print(f"\r{label} {frame}", end="", flush=True)
            time.sleep(0.15)
        print("\r" + " " * (len(label) + 2) + "\r", end="", flush=True)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive orangutan CLI")
    parser.add_argument(
        "--agents-dir",
        default="agents",
        help="Directory containing agent definitions.",
    )
    parser.add_argument(
        "--workflow-rules",
        default="workflow-rules/core-orangutan.md",
        help="Workflow rules path passed into TEAM MEMORY.",
    )
    parser.add_argument(
        "--use-mock-clis",
        action="store_true",
        help="Use bundled mock CLIs instead of real tools.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Maximum number of attempts when a pipeline run fails.",
    )
    parser.add_argument(
        "--task",
        help="Optional single-run task (non-interactive mode).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    console = OrangutanConsole(
        agents_dir=args.agents_dir,
        workflow_rules=args.workflow_rules,
        use_mock_clis=args.use_mock_clis,
        max_retries=max(1, args.retries),
    )
    if args.task:
        return console.run_single_task(args.task)
    return console.run()


if __name__ == "__main__":
    raise SystemExit(main())
