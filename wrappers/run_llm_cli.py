#!/usr/bin/env python3
"""Generic wrapper to run LLM CLIs in a non-interactive mode."""

from __future__ import annotations

import argparse
import json
import os
import select
import shlex
import subprocess
import sys
from typing import Any, List, Tuple


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
        elif prompt_mode == "positional":
            full_cmd.extend(["--", prompt])
        else:
            input_data = prompt

        if use_tty:
            try:
                returncode, stdout, stderr = run_with_pty(full_cmd, input_data or "")
            except OSError:
                returncode, stdout, stderr = run_with_script(
                    full_cmd,
                    input_data or "",
                )
        else:
            completed = subprocess.run(
                full_cmd,
                input=input_data,
                capture_output=True,
                text=True,
            )
            returncode = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
    except FileNotFoundError as exc:
        print(f"[run_llm_cli] CLI not found: {exc}", file=sys.stderr)
        return 1

    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)
    return returncode


def run_with_pty(cmd: List[str], data: str) -> Tuple[int, str, str]:
    import pty

    master_fd, slave_fd = pty.openpty()
    try:
        process = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            text=False,
        )
    finally:
        os.close(slave_fd)

    output_chunks: List[str] = []
    input_sent = False
    try:
        while True:
            if not input_sent:
                payload = data.encode("utf-8")
                if payload:
                    os.write(master_fd, payload)
                os.write(master_fd, b"\n")
                os.write(master_fd, b"\x04")
                input_sent = True

            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if master_fd in ready:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output_chunks.append(chunk.decode("utf-8", errors="ignore"))
            if process.poll() is not None and not ready:
                break
    finally:
        os.close(master_fd)

    returncode = process.wait()
    combined = "".join(output_chunks)
    return returncode, combined, ""


def run_with_script(cmd: List[str], data: str) -> Tuple[int, str, str]:
    quoted = " ".join(shlex.quote(part) for part in cmd)
    exec_cmd = ["script", "-q", "-e", "-c", quoted, "/dev/null"]
    completed = subprocess.run(
        exec_cmd,
        input=data,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""


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
        choices=["stdin", "flag", "positional"],
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
