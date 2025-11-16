#!/usr/bin/env python3
"""Interactive CLI that routes user prompts through the orangutan orchestrator."""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Tuple

try:
    import readline
except Exception:  # pragma: no cover - readline may not exist on Windows
    readline = None  # type: ignore

try:
    from rich.console import Console
    from rich.table import Table
except Exception:  # pragma: no cover - fallback if rich missing
    Console = None  # type: ignore
    Table = None  # type: ignore

from orchestrator import (
    PIPELINE_V01,
    Agent,
    execute_single_agent,
    initialize_state,
    load_all_agents,
)

SCENARIO_DESCRIPTIONS: Dict[str, str] = {
    "orchestrator": "coordinates the plan and delegates to each specialist",
    "analyst": "clarifies requirements and constraints before build work",
    "architect": "lays out the technical approach and module structure",
    "coder": "implements code and artifacts per the plan",
    "devops": "checks automation, environments, and runbooks",
    "reviewer": "audits the work for quality and correctness",
    "release-manager": "summarizes readiness and next steps",
}

ROLE_SUMMARY_FALLBACKS: Dict[str, List[str]] = {
    "orchestrator": [
        "Re-evaluated the task and delegated work across the pipeline.",
    ],
    "analyst": [
        "Clarified requirements and confirmed the scope for downstream agents.",
    ],
    "architect": [
        "Outlined the technical approach, dependencies, and guardrails.",
    ],
    "coder": [
        "Implemented or updated the necessary code artifacts for this task.",
    ],
    "devops": [
        "Adjusted automation, branching, or release workflows as needed.",
    ],
    "reviewer": [
        "Verified code quality and highlighted findings for the team.",
    ],
    "release-manager": [
        "Summarized progress and shared the next release/merge steps.",
    ],
}

STATUS_DESCRIPTIONS: Dict[str, str] = {
    "orchestrator": "Coordinating the plan",
    "analyst": "Shaping requirements",
    "architect": "Designing the solution",
    "coder": "Implementing changes",
    "devops": "Tending automation",
    "reviewer": "Reviewing quality",
    "release-manager": "Reporting readiness",
}


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
        self.custom_flow_note: Optional[str] = None
        self._history: List[str] = []
        self.console = Console() if Console else None
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
        self._setup_readline()
        while not self.shutdown_event.is_set():
            try:
                user_input = input("orangutan> ")
            except EOFError:
                print()
                break
            user_input = user_input.rstrip("\n")
            if not user_input:
                continue
            if user_input.lower() in {":q", "quit", "exit"}:
                break
            if user_input.lower() in {":help", "help"}:
                self._render_help()
                continue
            if user_input.lower().startswith(":flow"):
                self._handle_flow_command(user_input)
                continue
            self._history.append(user_input)
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
            "  :flow ... Configure or inspect the custom flow instructions\n"
            "Shortcuts:\n"
            "  Ctrl+C    Cancel the current run (press twice quickly to exit)\n"
            "  Ctrl+L    Clear the screen"
        )

    def _handle_flow_command(self, command: str) -> None:
        parts = command.split(" ", 1)
        if len(parts) == 1 or not parts[1].strip():
            note = self.custom_flow_note or "<none configured>"
            print(f"[orangutan] Current flow instructions: {note}")
            print(
                "  Usage: :flow <instructions> | :flow clear\n"
                "         (instructions will be passed to the orchestrator agent)"
            )
            return
        argument = parts[1].strip()
        if argument.lower() in {"clear", "reset"}:
            self.custom_flow_note = None
            print("[orangutan] Custom flow instructions cleared.")
        else:
            self.custom_flow_note = argument
            print(
                "[orangutan] Custom flow instructions set."
                " The orchestrator agent will adapt the scenario accordingly."
            )

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    def _dispatch_task(self, task: str) -> None:
        task = task.strip()
        if not task:
            return
        self.cancel_event.clear()
        effective_task = self._compose_task_with_flow(task)
        self._print_run_header(task)
        self._render_scenario()
        success = self._run_with_retries(effective_task)
        if self.console:
            panel_text = (
                "✅ Task completed successfully."
                if success
                else (
                    "⚠️ Task cancelled."
                    if self.cancel_event.is_set()
                    else "❌ Task failed after retries."
                )
            )
            self.console.rule()
            self.console.print(panel_text)
            self.console.rule()
        else:
            if success:
                print("[orangutan] ✅ Task completed successfully.\n")
            else:
                if self.cancel_event.is_set():
                    print("[orangutan] ⚠️  Task cancelled.\n")
                else:
                    print("[orangutan] ❌ Task failed after retries.\n")
        self.cancel_event.clear()

    def _run_with_retries(self, task: str) -> bool:
        state = initialize_state(task, self.workflow_rules)
        if self.custom_flow_note:
            state["project_context"]["custom_flow"] = self.custom_flow_note
        start_index = 0
        for attempt in range(1, self.max_retries + 1):
            if self.shutdown_event.is_set() or self.cancel_event.is_set():
                return False
            attempt_label = (
                f"[orangutan] Attempt {attempt}/{self.max_retries}"
                if start_index == 0
                else f"[orangutan] Attempt {attempt}/{self.max_retries} (resuming at {PIPELINE_V01[start_index]})"
            )
            print(attempt_label)
            success, failed_index = self._run_pipeline_once(
                task,
                state,
                start_index=start_index,
            )
            if success:
                return True
            if (
                failed_index is None
                or self.cancel_event.is_set()
                or self.shutdown_event.is_set()
            ):
                return False
            start_index = failed_index
            if attempt < self.max_retries:
                print(f"[orangutan] Retrying from agent {PIPELINE_V01[start_index]}…")
                self.cancel_event.clear()
                self.shutdown_event.clear()
        return False

    def _run_pipeline_once(
        self,
        task: str,
        state: Dict[str, Any],
        *,
        start_index: int = 0,
    ) -> Tuple[bool, Optional[int]]:
        statuses = {name: "pending" for name in PIPELINE_V01}
        start_times: Dict[str, float] = {}
        for idx in range(start_index, len(PIPELINE_V01)):
            name = PIPELINE_V01[idx]
            agent = self.agents.get(name)
            if not agent:
                print(f"[orangutan] Missing agent '{name}', skipping.")
                return False, idx
            if self.cancel_event.is_set() or self.shutdown_event.is_set():
                return False, None
            self._render_status_table(statuses, current=name)
            start_times[name] = time.perf_counter()
            self._log_agent_status(name, "running")
            agent_success = self._run_agent(agent, state, task)
            statuses[name] = "success" if agent_success else "failed"
            self._render_status_table(statuses)
            elapsed = time.perf_counter() - start_times.get(name, time.perf_counter())
            self._log_agent_status(name, statuses[name], elapsed)
            if not agent_success:
                return False, idx
        return True, None

    def _render_scenario(self) -> None:
        header = "[orangutan] Scenario overview:\n"
        flow_line = f"  Flow: {' → '.join(PIPELINE_V01)}"
        notes = []
        for name in PIPELINE_V01:
            desc = SCENARIO_DESCRIPTIONS.get(name)
            if desc:
                notes.append(f"  - {name}: {desc}")
        if self.custom_flow_note:
            notes.append("  Custom instructions: " + self.custom_flow_note)
        block = "\n".join([header.strip(), flow_line, *notes])
        if self.console:
            self.console.print(block)
        else:
            print(block)

    def _compose_task_with_flow(self, task: str) -> str:
        if not self.custom_flow_note:
            return task
        return (
            f"{task}\n\n"
            "The human operator requested these custom flow adjustments for the "
            f"orchestrator agent: {self.custom_flow_note}"
        )

    def _print_run_header(self, task: str) -> None:
        message = (
            f"\n[orangutan] Dispatching: {task}\n"
            "[orangutan] Breaking the task into steps and running the team "
            "in the documented workflow order…"
        )
        if self.console:
            self.console.rule()
            self.console.print(message)
            self.console.rule()
        else:
            print(message)

    def _setup_readline(self) -> None:
        if not readline:
            return
        for item in self._history:
            readline.add_history(item)
        readline.parse_and_bind("\C-l: clear-screen")

    def _render_status_table(
        self, statuses: Dict[str, str], current: Optional[str] = None
    ) -> None:
        if not self.console or not Table:
            return
        table = Table(box=None)
        table.add_column("Agent")
        table.add_column("Status")
        for name in PIPELINE_V01:
            status = statuses.get(name, "pending")
            if current == name and status == "pending":
                status = "running"
            icon = {
                "pending": "…",
                "running": "🟡",
                "success": "✅",
                "failed": "❌",
            }.get(status, status)
            table.add_row(name, icon)
        self.console.print(table)

    def _log_agent_status(
        self, name: str, status: str, elapsed: Optional[float] = None
    ) -> None:
        label = {
            "running": "[RUN ]",
            "success": "[ OK ]",
            "failed": "[FAIL]",
            "pending": "[....]",
        }.get(status, status)
        desc = STATUS_DESCRIPTIONS.get(name, "")
        message = f"{label} {name}"
        if desc:
            message += f" – {desc}"
        if status == "running":
            message += "… (press Ctrl+C to interrupt)"
        elif status == "success":
            message += " – done."
        elif status == "failed":
            message += " – failed."
        if status != "running" and elapsed is not None:
            message += f" ({format_duration(elapsed)})"
        if self.console:
            self.console.print(message)
        else:
            print(message)

    def _run_agent(self, agent: Agent, state: Dict[str, Any], task: str) -> bool:
        label = (
            f"{agent.name} – {STATUS_DESCRIPTIONS.get(agent.name, '').strip()}".strip(
                " –"
            )
        )
        status_cm = (
            self.console.status(f"[bold]{label}[/bold]")
            if self.console
            else nullcontext()
        )
        spinner_stop: Optional[threading.Event] = None
        spinner_thread: Optional[threading.Thread] = None
        if not self.console:
            spinner_stop = threading.Event()
            spinner_thread = threading.Thread(
                target=self._spinner_loop,
                args=(label, spinner_stop),
                daemon=True,
            )
            spinner_thread.start()
        with status_cm:
            agent_success, stdout, stderr = execute_single_agent(
                agent,
                state,
                task,
                use_mock_clis=self.use_mock_clis,
                verbose=False,
                on_process_start=self._track_process,
            )
        if spinner_stop and spinner_thread:
            spinner_stop.set()
            spinner_thread.join()
        summary_lines = self._prepare_summary(agent.name, stdout)
        icon = "✅" if agent_success else "❌"
        if self.console:
            self.console.print(f"{icon} [bold]{agent.name}[/bold]")
            for line in summary_lines:
                self.console.print(f"    {line}")
            if not agent_success and stderr:
                err_line = next(
                    (line for line in stderr.splitlines() if line.strip()),
                    "Unknown error",
                )
                self.console.print(f"    [red]error:[/red] {err_line}")
        else:
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

    def _prepare_summary(self, agent_name: str, stdout: str) -> List[str]:
        lines = (stdout or "").splitlines()
        summary = self._extract_summary_lines(lines)
        formatted: List[str] = []
        for line in summary:
            stripped = line.strip()
            if stripped.lower().startswith("openai codex v"):
                continue
            if stripped.lower().startswith(("workdir:", "model:", "provider:")):
                continue
            clean = stripped.lstrip("-*• ").strip()
            if not clean:
                continue
            formatted.append(f"- {clean}")
            if len(formatted) == 3:
                break
        if formatted:
            return formatted

        trimmed = [
            line
            for line in lines
            if line
            and not line.lower().startswith(
                ("openai codex v", "workdir:", "model:", "provider:")
            )
        ]
        fallback = ROLE_SUMMARY_FALLBACKS.get(agent_name.lower())
        if trimmed:
            formatted = [f"- {trimmed[0].strip()}"]
            formatted.extend(fallback or [])
            return formatted[:3]
        if fallback:
            return [f"- {text}" for text in fallback]
        return ["- Completed the step."]

    @staticmethod
    def _spinner_loop(label: str, stop_event: threading.Event) -> None:
        frames = "|/-\\"
        message = f"[RUN ] {label} "
        idx = 0
        while not stop_event.is_set():
            frame = frames[idx % len(frames)]
            idx += 1
            sys.stdout.write(f"\r{message}{frame}")
            sys.stdout.flush()
            if stop_event.wait(0.15):
                break
        sys.stdout.write("\r" + " " * (len(message) + 2) + "\r")
        sys.stdout.flush()

    @staticmethod
    def _extract_summary_lines(lines: List[str]) -> List[str]:
        collected: List[str] = []
        capture = False
        for raw in lines:
            line = raw.strip()
            if not line:
                if capture and collected:
                    break
                continue
            if line.startswith("## "):
                if line.upper().startswith("## SUMMARY"):
                    capture = True
                    continue
                if capture:
                    break
            if capture:
                collected.append(line)
        if not collected:
            collected = [ln for ln in (ln.strip() for ln in lines) if ln]
        return collected


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
        default=3,
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


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    mins, secs = divmod(seconds, 60)
    if mins and secs:
        return f"{mins}m {secs}s"
    if mins and not secs:
        return f"{mins}m"
    return f"{secs}s"


if __name__ == "__main__":
    raise SystemExit(main())
