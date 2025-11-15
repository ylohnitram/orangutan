#!/usr/bin/env python3
"""
Mock Gemini CLI used for local orchestration tests.

The script reads a JSON payload on stdin (matching orchestrator.py's contract)
and emits a lightweight markdown response so each pipeline stage has realistic
structured output without calling external LLMs.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any, Dict, List


def read_payload() -> Dict[str, Any]:
    """Load the JSON payload from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive path
        print(f"[mock_gemini] Invalid JSON payload: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def summarize_previous(state: Dict[str, Any]) -> str:
    """Return a short sentence about the last agent that ran."""
    history: List[Dict[str, Any]] = state.get("execution_history", [])
    if not history:
        return "No prior agent has run yet; initializing plan."
    last = history[-1]
    agent = last.get("agent", "unknown")
    status = "succeeded" if last.get("success") else "failed"
    return f"Previous agent `{agent}` {status} at {last.get('timestamp', 'unknown')}."


def format_artifact(payload: Dict[str, Any]) -> str:
    """Generate a JSON snippet with helpful context."""
    artifact = {
        "received_task": payload.get("task"),
        "workflow_rules": payload.get("workflow_rules", []),
        "state_keys": sorted(list((payload.get("state") or {}).keys())),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    return json.dumps(artifact, indent=2)


def main() -> int:
    payload = read_payload()
    state = payload.get("state") or {}
    task = payload.get("task") or "Unspecified task"
    agent_name = payload.get("agent_name", "analyst")

    summary_lines = [
        f"{agent_name} mock (Gemini flavor) evaluated task: **{task}**.",
        summarize_previous(state),
        "Outlined actionable guidance for the downstream engineer agents.",
    ]

    print("## SUMMARY")
    for line in summary_lines:
        print(f"- {line}")

    print("\n## ARTIFACTS")
    print("```json")
    print(format_artifact(payload))
    print("```")

    print("\n## NEXT_ACTION")
    print(
        "Hand off this plan to the next agent, ensuring they cross-check the "
        "workflow rules mentioned above."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
