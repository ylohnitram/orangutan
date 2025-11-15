#!/usr/bin/env python3
"""
v0.1.0 multi-CLI agent orchestrator.

Responsibilities (per architecture spec, simplified for v0.1.0):
- Load agent definitions from agents/*.yaml files.
- Initialize and maintain the TEAM MEMORY state object in memory.
- Execute agents in a hardcoded sequence:
    orchestrator → analyst → architect → coder → devops → reviewer → release-manager
- Invoke external CLI tools defined in each agent's frontmatter via subprocess.
- Log outputs to stdout / stderr and update TEAM MEMORY.
- Persist final TEAM MEMORY state to a JSON file for debugging.

NOTE:
- Workflow rules system is nicknamed "orangutan" in this codebase.
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml  # requires PyYAML

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
WRAPPER_SCRIPT = os.path.join(REPO_ROOT, "wrappers", "run_llm_cli.py")
MOCK_AGENT_SCRIPTS: Dict[str, str] = {
    "orchestrator": "mock_gemini.py",
    "analyst": "mock_gemini.py",
    "architect": "mock_claude.py",
    "coder": "mock_codex.py",
    "devops": "mock_claude.py",
    "reviewer": "mock_codex.py",
    "release-manager": "mock_gemini.py",
    "security": "mock_claude.py",
}
TOOL_WRAPPER_CONFIG: Dict[str, Dict[str, Any]] = {
    "gemini": {
        "cmd": ["--cmd", "gemini"],
        "prompt_mode": "flag",
        "prompt_flag": "--prompt",
    },
    "claude": {
        "cmd": ["--cmd", "claude", "--cmd", "chat"],
        "prompt_mode": "stdin",
    },
    "codex": {
        "cmd": ["--cmd", "codex", "--cmd", "exec"],
        "prompt_mode": "positional",
        "use_tty": True,
    },
}
PIPELINE_V01: List[str] = [
    "orchestrator",
    "analyst",
    "architect",
    "coder",
    "devops",
    "reviewer",
    "release-manager",
]


# ---------------------------------------------------------------------------
# Agent model and loader (lightweight inline version for v0.1.0)
# ---------------------------------------------------------------------------


@dataclass
class Agent:
    """In-memory representation of an agent definition."""

    name: str
    tool: str
    model: str
    role_prompt: str
    workflow_rules: List[str]


def load_agent(path: str) -> Agent:
    """Load a single agent .yaml file into an Agent object."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):  # pragma: no cover - defensive path
        raise TypeError(f"Agent file must define a mapping: {path}")

    name = data.get("name") or os.path.splitext(os.path.basename(path))[0]
    tool = data.get("tool")
    if not tool:
        raise ValueError(f"Agent '{name}' missing 'tool' in {path}")

    model = data.get("model")
    if not model:
        raise ValueError(f"Agent '{name}' missing 'model' in {path}")

    role_prompt = data.get("role_prompt") or data.get("prompt") or ""
    workflow_rules = data.get("workflow_rules") or []
    if isinstance(workflow_rules, str):
        workflow_rules = [workflow_rules]

    return Agent(
        name=name,
        tool=tool,
        model=model,
        role_prompt=role_prompt.strip(),
        workflow_rules=workflow_rules,
    )


def load_all_agents(agents_dir: str) -> Dict[str, Agent]:
    """
    Load all agents from a directory.

    Returns:
        dict mapping agent.name -> Agent
    """
    agents: Dict[str, Agent] = {}

    if not os.path.isdir(agents_dir):
        raise FileNotFoundError(f"Agents directory not found: {agents_dir}")

    for entry in sorted(os.listdir(agents_dir)):
        if not entry.endswith(".yaml"):
            continue
        path = os.path.join(agents_dir, entry)
        agent = load_agent(path)
        agents[agent.name] = agent

    return agents


def build_agent_command(agent: Agent, use_mock_clis: bool) -> List[str]:
    """Return the subprocess command for an agent."""
    if use_mock_clis:
        script = MOCK_AGENT_SCRIPTS.get(agent.name)
        if script:
            script_path = os.path.join(REPO_ROOT, script)
            return [sys.executable, script_path]

    config = TOOL_WRAPPER_CONFIG.get(agent.tool)
    if not config:
        raise ValueError(f"No wrapper configuration for tool '{agent.tool}'")

    cmd: List[str] = [sys.executable, WRAPPER_SCRIPT]
    cmd.extend(config.get("cmd", []))
    if agent.model:
        cmd.extend(["--model", agent.model])

    prompt_mode = config.get("prompt_mode", "stdin")
    cmd.extend(["--prompt-mode", prompt_mode])
    if prompt_mode == "flag":
        prompt_flag = config.get("prompt_flag")
        if not prompt_flag:
            raise ValueError(
                f"Tool '{agent.tool}' uses flag prompt mode but missing prompt_flag"
            )
        cmd.append(f"--prompt-flag={prompt_flag}")

    extra_args = config.get("extra_args") or []
    cmd.extend(extra_args)
    if config.get("use_tty"):
        cmd.append("--use-tty")
    return cmd


# ---------------------------------------------------------------------------
# TEAM MEMORY state management (minimal v0.1.0)
# ---------------------------------------------------------------------------


def initialize_state(task: str, workflow_rules_path: str) -> Dict[str, Any]:
    """
    Create the initial TEAM MEMORY state object.

    Structure (simplified):

    state = {
        "project_context": {
            "name": "multi-cli-agent-orchestrator",
            "version": "v0.1.0",
            "goal": "Build and run the v0.1.0 multi-CLI agent orchestration pipeline",
            "current_task": <task>,
        },
        "agent_outputs": {
            # Filled incrementally by execute_single_agent(...)
        },
        "workflow_rules": {
            "system": "orangutan",
            "loaded_from": <workflow_rules_path>,
            "rules": [],  # v0.1.0 stub: rules not parsed/enforced
        },
        "execution_history": [
            # {
            #   "agent": str,
            #   "timestamp": str,
            #   "success": bool,
            #   "error": str | None,
            # }
        ],
    }
    """
    state: Dict[str, Any] = {
        "project_context": {
            "name": "multi-cli-agent-orchestrator",
            "version": "v0.1.0",
            "goal": "Build and run the v0.1.0 multi-CLI agent orchestration pipeline",
            "current_task": task,
        },
        "agent_outputs": {},
        "workflow_rules": {
            "system": "orangutan",
            "loaded_from": workflow_rules_path,
            "rules": [],
        },
        "execution_history": [],
    }
    return state


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------


def execute_single_agent(
    agent: Agent,
    state: Dict[str, Any],
    task: str,
    use_mock_clis: bool = False,
    *,
    verbose: bool = True,
    on_process_start: Optional[Callable[[Optional[subprocess.Popen]], None]] = None,
) -> Tuple[bool, str, str]:
    """
    Execute one agent via subprocess and update TEAM MEMORY.

    - Builds a simple JSON payload with agent metadata, task, and current state.
    - Sends payload to the agent CLI over stdin.
    - Captures stdout/stderr and return code.
    - Logs basic info to stdout / stderr.
    - Stores the raw stdout as agent_outputs[agent.name]["summary"].
    - When use_mock_clis is True, swap CLI execution to mock_* scripts.

    Returns:
        Tuple of (success flag, stdout, stderr).

    TODO:
    - In a later version, parse structured sections (SUMMARY/ARTIFACTS/NEXT_ACTION).
    """
    payload = {
        "agent_name": agent.name,
        "role_prompt": agent.role_prompt,
        "task": task,
        "state": state,
        "workflow_rules": agent.workflow_rules,
    }
    input_text = json.dumps(payload, indent=2)

    cmd = build_agent_command(agent, use_mock_clis)
    started_at = datetime.utcnow().isoformat() + "Z"

    # Ensure agent commands can access the same interpreter/venv as the orchestrator.
    env = os.environ.copy()
    python_dir = os.path.dirname(sys.executable)
    if python_dir:
        existing_path = env.get("PATH", "")
        path_parts = existing_path.split(os.pathsep) if existing_path else []
        if python_dir not in path_parts:
            env["PATH"] = (
                os.pathsep.join([python_dir, existing_path])
                if existing_path
                else python_dir
            )

    stdout = ""
    stderr = ""
    success = False
    process: Optional[subprocess.Popen[str]] = None
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        if on_process_start:
            on_process_start(process)
        stdout, stderr = process.communicate(input=input_text)
        stdout = (stdout or "").strip()
        stderr = (stderr or "").strip()
        success = process.returncode == 0
    except FileNotFoundError as exc:
        stderr = f"Failed to execute agent command: {exc}"
        stdout = ""
        success = False
    except KeyboardInterrupt:
        if process and process.poll() is None:
            process.terminate()
        raise
    finally:
        if on_process_start:
            on_process_start(None)

    separator = "=" * 80
    if verbose:
        print(separator)
        print(f"[orchestrator] Agent: {agent.name}")
        print(f"[orchestrator] Command: {' '.join(cmd)}")
        print(f"[orchestrator] Success: {success}")
        if stdout:
            print(f"[orchestrator] STDOUT:\n{stdout}")
        if stderr:
            print(f"[orchestrator] STDERR:\n{stderr}", file=sys.stderr)

    # Minimal state update: store raw output as summary
    state["agent_outputs"][agent.name] = {
        "summary": stdout,
        "artifacts": {},  # Reserved for future structured parsing
        "next_action": "",  # Reserved for future NEXT_ACTION parsing
    }

    # Append execution history entry
    state["execution_history"].append(
        {
            "agent": agent.name,
            "timestamp": started_at,
            "success": success,
            "error": None if success else (stderr or "Unknown error"),
        }
    )

    return success, stdout, stderr


def run_v01_pipeline(
    agents: Dict[str, Agent],
    state: Dict[str, Any],
    task: str,
    use_mock_clis: bool = False,
    *,
    verbose: bool = True,
    progress_callback: Optional[
        Callable[[str, bool, str, str, Dict[str, Any]], None]
    ] = None,
    on_process_start: Optional[Callable[[Optional[subprocess.Popen]], None]] = None,
    start_index: int = 0,
) -> Tuple[bool, Optional[int]]:
    """
    Run the hardcoded v0.1.0 pipeline and return (success, failed_agent_index).
    """
    for idx in range(start_index, len(PIPELINE_V01)):
        name = PIPELINE_V01[idx]
        agent = agents.get(name)
        if not agent:
            print(
                f"[orchestrator] WARNING: Agent '{name}' not found; skipping",
                file=sys.stderr,
            )
            return False, idx
        success, stdout, stderr = execute_single_agent(
            agent,
            state,
            task,
            use_mock_clis=use_mock_clis,
            verbose=verbose,
            on_process_start=on_process_start,
        )
        if progress_callback:
            progress_callback(agent.name, success, stdout, stderr, state)
        if not success:
            return False, idx
    return True, None


def save_state(state: Dict[str, Any], path: str) -> None:
    """Persist TEAM MEMORY state to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="v0.1.0 multi-CLI agent orchestrator",
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Natural language description of the task for the agent team.",
    )
    parser.add_argument(
        "--agents-dir",
        default="agents",
        help="Directory containing agent .md definitions.",
    )
    parser.add_argument(
        "--workflow-rules",
        default="workflow-rules/core-orangutan.md",
        help="Path to core workflow rules file (orangutan).",
    )
    parser.add_argument(
        "--state-path",
        default="state.json",
        help="Path to write final TEAM MEMORY state as JSON.",
    )
    parser.add_argument(
        "--use-mock-clis",
        action="store_true",
        help="Use the bundled mock_* scripts instead of the configured CLI commands.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    try:
        agents = load_all_agents(args.agents_dir)
    except Exception as exc:  # noqa: BLE001 (simple top-level error handling)
        print(f"[orchestrator] ERROR: {exc}", file=sys.stderr)
        return 1

    if not agents:
        print(
            f"[orchestrator] ERROR: No agents loaded from {args.agents_dir}",
            file=sys.stderr,
        )
        return 1

    state = initialize_state(args.task, args.workflow_rules)
    pipeline_success, failed_index = run_v01_pipeline(
        agents,
        state,
        args.task,
        use_mock_clis=args.use_mock_clis,
    )
    save_state(state, args.state_path)
    print(f"[orchestrator] Saved TEAM MEMORY state to {args.state_path}")
    if not pipeline_success:
        if failed_index is not None:
            failed_agent = PIPELINE_V01[failed_index]
            print(
                f"[orchestrator] Failed while executing agent '{failed_agent}'",
                file=sys.stderr,
            )
        else:
            print(
                "[orchestrator] Completed with at least one agent failure",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
