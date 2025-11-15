## RELEASE_TAG
* `v0.1.0-orchestrator-bootstrap`

---

## WHAT’S_INCLUDED
* **Orchestrator Script (`orchestrator.py`):** A Python script that serves as the v0.1.0 orchestrator.
* **Agent Loading:** The orchestrator loads agent definitions (CLI commands, prompts) from `agents/*.md` files.
* **Hardcoded Pipeline:** The script executes a fixed, hardcoded sequence of agents: `analyst` → `architect` → `coder` → `devops` → `reviewer` → `release-manager`.
* **State Management ("TEAM MEMORY"):** A "TEAM MEMORY" state object is initialized in memory, passed to each agent via `stdin`, and updated with their raw `stdout`.
* **State Persistence:** The final TEAM MEMORY object is saved to a JSON file (e.g., `state-local.json` or `state-ci.json`) for debugging.
* **Makefile Automation:** A `Makefile` provides helper targets to manage the environment and run the pipeline:
    * `make install`: Sets up the `.venv/` and installs dependencies.
    * `make run-pipeline`: Runs a local smoke test.
    * `make run-pipeline-ci`: Runs the CI-specific smoke test.
* **CI Smoke Test:** A GitHub Actions workflow (`orchestrator-smoke-test.yml`) automatically runs `make run-pipeline-ci` on pushes and pull requests to the `main` or `master` branches.

---

## HOW_TO_RUN_LOCALLY
1.  **Prerequisite:** Ensure all required LLM CLI tools (e.g., Gemini, Claude, ChatGPT) are installed, authenticated, and available in your system's `PATH`.
2.  **Install Dependencies:** From a fresh clone of the repository, run `make install`. This creates a local Python virtual environment in `.venv/` and installs the packages listed in `requirements.txt`.
3.  **Run Pipeline:** Execute `make run-pipeline`. This will:
    * Activate the virtualenv.
    * Run `orchestrator.py` with the local smoke test task.
    * Execute the full hardcoded pipeline of agents.
4.  **Verify Output:** Monitor the console for logs from the orchestrator and each agent. After completion, inspect the final `state-local.json` file to see the final TEAM MEMORY state.

---

## HOW_TO_RUN_CI
* **What it does:** The GitHub Actions workflow "Orchestrator CI Smoke Test" is triggered on every push or pull request to the `main` and `master` branches. It checks out the code, sets up Python 3.11, and runs the `make run-pipeline-ci` target.
* **Success/Failure:**
    * A **successful** run means the `install` target completed and the `orchestrator.py` script executed from start to finish without crashing (exited with code 0).
    * A **failed** run indicates an issue with dependency installation, a syntax error, or a runtime crash in the orchestrator script. This is our basic "smoke test" to ensure the core pipeline logic is not broken.

---

## KNOWN_LIMITATIONS
* **Hardcoded Pipeline:** The agent execution sequence is static and defined in the `run_v01_pipeline` function. The orchestrator cannot yet make decisions about which agent to run next.
* **Workflow Rules Not Enforced:** The orchestrator loads the *path* to the `core-orangutan.md` rules file, but the rules themselves are not parsed or enforced.
* **Simplistic State:** The orchestrator only stores the raw `stdout` from an agent as its "summary". It does not parse structured output (like artifacts or "next action" commands).
* **Incomplete Agent Roster:** The `security` agent (defined in `agents/security.md`) is not included in the hardcoded v0.1.0 pipeline.
* **Minimal Error Handling:** If an agent subprocess fails, its error is logged, but the orchestrator simply proceeds to the next agent in the hardcoded sequence.

---

## NEXT_STEPS_FOR_V0_2
* **Introduce a "Metaprompt" Orchestrator Agent:** Add a new `orchestrator` agent whose job is to analyze the TEAM MEMORY state and decide *which agent* to run next, replacing the hardcoded pipeline.
* **Implement Structured Output:** Define a clear Markdown-based format for agent outputs (e.g., `## SUMMARY`, `## ARTIFACTS`, `## NEXT_ACTION`) and teach the orchestrator to parse it.
* **Dynamic Agent Execution:** Use the parsed `NEXT_ACTION` field (e.g., `NEXT_ACTION: call_agent(coder)`) to drive the pipeline dynamically.
* **Workflow Rule Enforcement:** Begin parsing `core-orangutan.md` and use its rules to constrain agent prompts or validate their outputs.
* **Integrate a QA Agent:** Add a `qa` agent to the pipeline, perhaps running after `coder`, to autonomously test code artifacts before the `reviewer` is called.
* **Improve Error Handling:** Implement a basic strategy for handling agent failures (e.g., route to `devops` or `coder` for a fix) instead of just logging and continuing.
