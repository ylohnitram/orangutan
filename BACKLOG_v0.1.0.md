## CONTEXT_SUMMARY
* The specification describes a multi-agent orchestration system based on individual `.md` agent definitions.
* Agent definitions include YAML frontmatter to specify which CLI tool to execute (e.g., `gemini`, `claude`, `codex`).
* The system uses a shared `TEAM MEMORY` (a state object) to pass context between stateless agents.
* Agents have a standardized I/O contract, receiving a prompt with the `TEAM MEMORY` and returning a structured response (SUMMARY, ARTIFACTS, NEXT_ACTION).
* Workflow rules are defined in a separate `workflow-rules/` directory and loaded into the state.
* The user's goal is a **v0.1.0 minimal viable product (MVP)** to validate the core pipeline.
* The v0.1.0 scope includes the `architect`, `coder`, `devops`, `reviewer`, and `release-manager` agents, run by a minimal Python script.

## REQUIREMENTS

### Functional Requirements
* **FR-1:** The `orchestrator.py` script must be able to load an agent's `.md` file from the `agents/` directory.
* **FR-2:** The script must parse the agent's YAML frontmatter to identify its `cli.command` and `cli.args`.
* **FR-3:** The script must load the agent's prompt (body of the `.md` file).
* **FR-4:** The script must maintain a Python representation of the `TEAM MEMORY` (state object).
* **FR-5:** The script must construct the full input prompt for an agent by combining its role, the `TEAM MEMORY`, and a specific task, following the template in Spec 5.1.
* **FR-6:** The script must execute the agent's defined `cli.command` as a subprocess, passing the constructed prompt as standard input (`stdin`).
* **FR-7:** The script must capture the agent's response from standard output (`stdout`).
* **FR-8:** The script must parse the agent's structured response (headers `## SUMMARY`, `## ARTIFACTS`, etc.) to update the `TEAM MEMORY`.

### Non-Functional Requirements
* **NFR-1 (Simplicity):** The v0.1.0 `orchestrator.py` must be minimal, containing no complex routing logic. It can hardcode the v0.1.0 agent sequence.
* **NFR-2 (CLI-Based):** The system *must* interact with LLMs via external CLI tools (subprocess execution), not direct API calls.
* **NFR-3 (Multi-LLM):** The orchestrator must support invoking different CLIs for different agents (e.g., running `gemini` for one agent and `codex` for another).

## BACKLOG

### For architect
* **[ARCH-1]** Define the Python data structures for the `TEAM MEMORY` (based on Spec section 4) and the `Agent` object (loaded from `.md` frontmatter and body).
* **[ARCH-2]** Design the main execution flow for the minimal `orchestrator.py` script, detailing the sequence: 1. Load Agent, 2. Build Prompt, 3. Execute Subprocess, 4. Parse Output, 5. Update State.
* **[ARCH-3]** Specify the precise I/O contract for the subprocess wrapper, clarifying how the prompt is passed to `stdin` and how `stdout` is read and returned.

### For coder
* **[CODE-1]** Implement a Python utility function to load an agent's `.md` file, parsing its YAML frontmatter (using `PyYAML`) and its Markdown body.
* **[CODE-2]** Implement the core Python function (`execute_agent`) that takes an `Agent` object and the current `TEAM MEMORY` (state), constructs the full prompt (per Spec 5.1), and runs the agent's `cli.command` + `cli.args` as a subprocess, capturing and returning the `stdout`.
* **[CODE-3]** Implement a Python utility function to parse the structured `stdout` response from an agent into a dictionary (e.g., keys: `summary`, `artifacts`, `next_action`) based on the headers in Spec 5.2.
* **[CODE-4]** Implement the main `orchestrator.py` script. For v0.1.0, this script can be a simple, linear program that loads the state, calls `execute_agent` for `architect`, updates state, calls `execute_agent` for `coder`, and so on for the 5 agents.

### For devops
* **[DEVOPS-1]** Create the base directory structure: `project-root/`, `agents/`, and `workflow-rules/`.
* **[DEVOPS-2]** Create placeholder `.md` files for the five v0.1.0 agents (`architect.md`, `coder.md`, `devops.md`, `reviewer.md`, `release-manager.md`) in the `agents/` directory, populating them with the content from Spec sections 3.2, 3.3, 3.5, 3.10, and 3.9.
* **[DEVOPS-3]** Create a placeholder `workflow-rules/core-orangutan.md` file.
* **[DEVOPS-4]** Create a `requirements.txt` file for the Python orchestrator, including `PyYAML` as a dependency.
* **[DEVOPS-5]** Create the empty `orchestrator.py` file.

### For reviewer
* **[REV-1]** Review the `orchestrator.py` implementation, verifying that it correctly executes CLI commands as subprocesses and parses the structured response according to the I/O contract (Spec 5.1, 5.2).
* **[REV-2]** Ensure the Python code for state management and prompt generation aligns with the `architect`'s design (ARCH-1, ARCH-2).

### For release-manager
* **[REL-1]** Define the "Done" criteria for v0.1.0: A human must be able to run the `orchestrator.py` script and successfully execute the five-agent pipeline (architect -> coder -> devops -> reviewer -> release-manager) against a single test issue, with the state being correctly passed and updated at each step.

## RISKS_AND_OPEN_QUESTIONS
* **[RISK-1]** The system's reliability is highly dependent on the LLM agents *perfectly* adhering to the structured output format (Spec 5.2). If an agent fails to provide the exact headers, the parsing logic (CODE-3) will fail.
* **[RISK-2]** The v0.1.0 scope excludes the `qa-engineer` agent. This places the full burden of testing the orchestrator's logic on the `reviewer` and `release-manager`.
* **[RISK-3]** Subprocess management can be complex. The `coder` implementation must handle potential errors, hangs, or non-zero exit codes from the external CLI tools.
* **[QUESTION-1]** Does the `architect` envision the v0.1.0 `orchestrator.py` as a single-run script, or as a tool that the human orchestrator invokes step-by-step (e.g., `python orchestrator.py --agent coder --state-file state.json`)?
* **[QUESTION-2]** Are the external CLIs (`gemini`, `claude`, etc.) assumed to be pre-installed and authenticated on the host machine? This assumption must be true for `DEVOPS-4` and `CODE-2` to be valid.
