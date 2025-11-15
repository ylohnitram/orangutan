#!/usr/bin/env python3
"""
Mock Claude CLI for orchestrator development.

Behaves like a deterministic CLI agent that consumes the orchestrator payload
and emits markdown so the pipeline can move forward without networked LLMs.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any, Dict, List


def read_payload() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive path
        print(f"[mock_claude] Invalid JSON payload: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def summarize_agent_outputs(state: Dict[str, Any]) -> str:
    outputs: Dict[str, Any] = state.get("agent_outputs", {})
    if not outputs:
        return "No agent outputs yet; creating initial technical blueprint."
    completed = ", ".join(sorted(outputs.keys()))
    return f"Technical context already supplied by: {completed}."


def make_artifact(payload: Dict[str, Any]) -> str:
    snippet = {
        "agent": payload.get("agent_name"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "notes": "Structured hand-off prepared by mock_claude.",
    }
    return json.dumps(snippet, indent=2)


def main() -> int:
    payload = read_payload()
    state = payload.get("state") or {}
    task = payload.get("task") or "Unspecified task"
    agent_name = payload.get("agent_name", "architect")

    summary_lines = [
        f"{agent_name} mock (Claude flavor) translated the task into a "
        f"concrete plan: **{task}**.",
        summarize_agent_outputs(state),
        "Ensured assumptions align with orangutan workflow rules.",
    ]

    print("## SUMMARY")
    for line in summary_lines:
        print(f"- {line}")

    print("\n## ARTIFACTS")
    print("```json")
    print(make_artifact(payload))
    print("```")

    print("\n## NEXT_ACTION")
    print(
        "Provide these structured notes to the coder so they can implement or "
        "validate the described changes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
