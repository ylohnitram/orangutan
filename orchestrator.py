#!/usr/bin/env python3
"""
v0.1.0 multi-CLI agent orchestrator.

Responsibilities (per architecture spec, simplified for v0.1.0):
- Load agent definitions from agents/*.md files.
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
    cli_command: str
    cli_args: List[str]
    role_prompt: str
    workflow_rules: List[str]


def parse_frontmatter_and_body(path: str):
    """
    Parse a markdown file with YAML frontmatter.

    Expected format:

    ---
    name: agent-name
    cli_command: python
    cli_args:
      - mock_tool.py
    role_prompt: |
      ...
    workflow_rules:
      - workflow-rules/core-orangutan.md
    ---
    # Markdown body ...

    Returns:
        (frontmatter: dict, body: str)
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    if not text.startswith("---"):
        raise ValueError(f"No YAML frontmatter found in agent file: {path}")

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Incomplete YAML frontmatter in agent file: {path}")

    yaml_text = parts[1]
    body = parts[2].lstrip("\n")

    frontmatter = yaml.safe_load(yaml_text) or {}
    return frontmatter, body


def load_agent(path: str) -> Agent:
    """Load a single agent .md file into an Agent object."""
    frontmatter, body = parse_frontmatter_and_body(path)

    name = frontmatter.get("name") or os.path.splitext(os.path.basename(path))[0]
    cli_command = frontmatter.get("cli_command")
    if not cli_command:
        raise ValueError(f"Agent '{name}' missing 'cli_command' in {path}")

    cli_args = frontmatter.get("cli_args") or []
    if not isinstance(cli_args, list):
        raise TypeError(f"'cli_args' for agent '{name}' must be a list")

    role_prompt = frontmatter.get("role_prompt") or body or ""
    workflow_rules = frontmatter.get("workflow_rules") or []
    if isinstance(workflow_rules, str):
        workflow_rules = [workflow_rules]

    return Agent(
        name=name,
        cli_command=cli_command,
        cli_args=cli_args,
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
        if not entry.endswith(".md"):
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

    cmd = [agent.cli_command] + agent.cli_args
    if agent.cli_command in {"python", "python3"}:
        cmd = [sys.executable] + agent.cli_args
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
) -> bool:
    """
    Run the hardcoded v0.1.0 pipeline and return True if all agents succeeded.
    """
    overall_success = True
    for name in PIPELINE_V01:
        agent = agents.get(name)
        if not agent:
            print(
                f"[orchestrator] WARNING: Agent '{name}' not found; skipping",
                file=sys.stderr,
            )
            overall_success = False
            continue
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
            overall_success = False
    return overall_success


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
    pipeline_success = run_v01_pipeline(
        agents,
        state,
        args.task,
        use_mock_clis=args.use_mock_clis,
    )
    save_state(state, args.state_path)
    print(f"[orchestrator] Saved TEAM MEMORY state to {args.state_path}")
    if not pipeline_success:
        print(
            "[orchestrator] Completed with at least one agent failure",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
