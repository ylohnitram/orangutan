# Makefile for FlowLint / orangutan v0.1.0 orchestrator
#
# Usage:
#   make run-pipeline      # local smoke test
#   make run-pipeline-ci   # CI smoke test (also usable locally)
#
# Note:
#   - This Makefile creates a local virtualenv in .venv/
#   - LLM CLI tools (Gemini, Claude, ChatGPT, Q) are assumed to be
#     installed and pre-configured via their own OAuth login flows
#     (flat tariff). No API keys or secrets are read from env here.

PYTHON ?= python3
VENV_DIR ?= .venv
PIP := $(VENV_DIR)/bin/pip
PYTHON_VENV := $(VENV_DIR)/bin/python

.PHONY: venv install run-pipeline run-pipeline-ci clean

venv:
	$(PYTHON) -m venv $(VENV_DIR)

install: venv requirements.txt
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

# Local developer-friendly pipeline run
run-pipeline: install
	$(PYTHON_VENV) orchestrator.py \
		--task "DevOps local smoke test for FlowLint multi-CLI orchestrator" \
		--state-path state-local.json

# CI-focused pipeline run (can also be used locally)
run-pipeline-ci: install
	$(PYTHON_VENV) orchestrator.py \
		--task "DevOps CI smoke test for FlowLint multi-CLI orchestrator" \
		--state-path state-ci.json

clean:
	rm -rf $(VENV_DIR) state-local.json state-ci.json state.json
