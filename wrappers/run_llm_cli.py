#!/usr/bin/env python3
"""Generic wrapper to run LLM CLIs in a non-interactive mode."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from typing import Any, List


def read_payload() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        print(f"[run_llm_cli] Invalid JSON payload: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def build_prompt(payload: dict[str, Any]) -> str:
    role_prompt = payload.get("role_prompt", "")
    task = payload.get("task", "")
    workflow_rules = payload.get("workflow_rules", [])
    state = payload.get("state", {})

    prompt_parts = [
        role_prompt.strip(),
        "",
        "## TASK",
        task.strip(),
        "",
        "## WORKFLOW RULES",
        "\n".join(workflow_rules) if workflow_rules else "(none)",
        "",
        "## TEAM MEMORY (JSON)",
        json.dumps(state, indent=2),
        "",
        "Produce your response using the sections:",
        "## SUMMARY",
        "## ARTIFACTS",
        "## NEXT_ACTION",
    ]
    return "\n".join(part for part in prompt_parts if part is not None)


def run_cli(
    cmd: List[str],
    prompt: str,
    prompt_mode: str,
    prompt_flag: str | None,
    use_tty: bool,
) -> int:
    try:
        input_data = None
        full_cmd = list(cmd)
        if prompt_mode == "flag":
            if not prompt_flag:
                raise SystemExit("--prompt-flag is required when prompt-mode=flag")
            full_cmd.extend([prompt_flag, prompt])
        else:
            input_data = prompt

        if use_tty:
            quoted = " ".join(shlex.quote(part) for part in full_cmd)
            exec_cmd = ["script", "-q", "-e", "-c", quoted, "/dev/null"]
        else:
            exec_cmd = full_cmd

        completed = subprocess.run(
            exec_cmd,
            input=input_data,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        print(f"[run_llm_cli] CLI not found: {exc}", file=sys.stderr)
        return 1

    if completed.stdout:
        print(completed.stdout.strip())
    if completed.stderr:
        print(completed.stderr.strip(), file=sys.stderr)
    return completed.returncode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an LLM CLI with orchestrator payloads"
    )
    parser.add_argument(
        "--cmd",
        action="append",
        required=True,
        help="Command part to execute (repeat for subcommands)",
    )
    parser.add_argument(
        "--model",
        help="Model identifier to append as '--model <value>'",
    )
    parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Additional CLI arguments appended before the prompt",
    )
    parser.add_argument(
        "--prompt-mode",
        choices=["stdin", "flag"],
        default="stdin",
        help="How to pass the prompt to the CLI",
    )
    parser.add_argument(
        "--prompt-flag",
        help="Flag name used when prompt-mode=flag (e.g., --text)",
    )
    parser.add_argument(
        "--use-tty",
        action="store_true",
        help="Wrap the CLI execution in a pseudo-TTY using the 'script' command.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = read_payload()
    prompt = build_prompt(payload)

    command = list(args.cmd)
    if args.model:
        command.extend(["--model", args.model])
    if args.extra_arg:
        command.extend(args.extra_arg)

    return run_cli(
        command,
        prompt,
        args.prompt_mode,
        args.prompt_flag,
        args.use_tty,
    )


if __name__ == "__main__":
    raise SystemExit(main())
