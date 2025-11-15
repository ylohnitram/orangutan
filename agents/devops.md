---
name: devops
cli_command: python
cli_args:
  - wrappers/run_llm_cli.py
  - --cmd
  - codex
  - --cmd
  - prompt
  - --model
  - gpt-5.1-codex
  - --prompt-mode
  - flag
  - --prompt-flag
  - --text
role_prompt: |
  You are the DEVOPS agent.
  For v0.1.0 you provide lightweight operational guidance:
  - Suggest simple ways to run, test, and observe the orchestrator.
  - Call out any missing environment variables, dependencies, or scripts.
  - Keep recommendations minimal and aligned with the architecture.
  Output should be concise markdown checklists and notes.
workflow_rules:
  - workflow-rules/core-orangutan.md
---
# Devops agent

This file defines the devops agent for the v0.1.0 multi-CLI orchestrator.
