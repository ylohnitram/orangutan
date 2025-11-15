# Repository Guidelines

## Project Structure & Module Organization
- `orchestrator.py` is the single entrypoint and must keep the documented load → execute → persist flow from `ARCHITECTURE_v0.1.0.md`.
- Agent prompts and CLI definitions live in `agents/*.md` with YAML front matter (`name`, `cli_command`, `cli_args`, `workflow_rules`); align prompts with `workflow-rules/core-orangutan.md`.
- Product docs (`BACKLOG_v0.1.0.md`, `TODO.md`, `multi_agent_orchestrator_spec.md`) record intent—update them when behavior shifts.
- Pipeline runs emit `state-*.json` for debugging only; never commit those artifacts.

## Build, Test, and Development Commands
- `make VENV_DIR=/home/$USER/.venvs/orangutan install` — preferred WSL invocation; creates a venv under the Linux filesystem, upgrades `pip`, and installs `requirements.txt`.
- `make install` — default target for non-WSL setups; creates `.venv`, upgrades `pip`, and installs `requirements.txt` (PyYAML only).
- `make run-pipeline` — runs the orchestration loop locally with `state-local.json`; fastest way to smoke test a change.
- `make run-pipeline-ci` — mirrors the CI task definition, writing `state-ci.json`; use it before opening a PR.
- `make clean` — deletes `.venv` and transient state files when a fresh run is needed.

## Coding Style & Naming Conventions
- Target Python 3.11+, 4-space indentation, and full type hints. Dataclasses suit shared models; keep the existing ruler-comment sections.
- Prefer verb-based function names (`load_agent`), UPPER_SNAKE_CASE constants, and reserve camelCase JSON keys for external API compatibility.
- Format with `python -m black orchestrator.py` followed by `python -m isort orchestrator.py` before every PR.

## Testing Guidelines
- Create a `tests/` directory when adding unit coverage; use pytest, naming files `test_<module>.py`, and keep reusable fixtures in `tests/fixtures/`.
- Document integration proof by running `make run-pipeline` and summarizing agent order (`analyst → architect → coder → devops → reviewer → release-manager`) plus notable logs in the PR.
- Stabilize runs by pinning mock agent CLIs or clearly stating any required external tools.

## Commit & Pull Request Guidelines
- Follow the observed Conventional Commit style (`feat:`, `doc:`, etc.) and keep commits tightly scoped with imperative subjects referencing issues when relevant.
- Exclude generated state files, describe testing evidence (`make run-pipeline` or similar), and call out every agent or doc touched in the PR description alongside screenshots/log snippets when behavior shifts.

## Security & Configuration Tips
- Agent CLIs often call proprietary LLM tools—never hardcode tokens in agent files or workflow rules, and rely on each contributor’s local CLI auth.
- When adding or modifying CLI definitions, review `orchestrator.py` safety checks (timeouts, argument validation) and expand `workflow-rules/core-orangutan.md` if extra guardrails are needed.
