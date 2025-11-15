## ARCHITECTURE_OVERVIEW

The v0.1.0.0.0.0.0.0.0.0 multi-agent orchestrator is a minimal Python system that executes a fixed pipeline of 5 LLM agents (architect, coder, devops, reviewer, release-manager) via CLI subprocesses. Each agent is defined as a Markdown file with YAML frontmatter specifying its CLI command. The orchestrator maintains a shared state object (TEAM MEMORY) that gets passed to each agent and updated with their outputs. This MVP validates the core concept of CLI-based multi-LLM orchestration with structured I/O contracts.

## FILE_STRUCTURE
```
project-root/
├── orchestrator.py           # Main orchestration script
├── agent_loader.py          # Utility for loading/parsing agent .md files
├── agent_executor.py        # Subprocess execution wrapper
├── response_parser.py       # Parser for structured agent responses
├── state_manager.py         # TEAM MEMORY state management
├── requirements.txt         # Python dependencies (PyYAML)
├── agents/
│   ├── architect.md         # Agent definition with frontmatter
│   ├── coder.md            # Agent definition with frontmatter
│   ├── devops.md           # Agent definition with frontmatter
│   ├── reviewer.md         # Agent definition with frontmatter
│   └── release-manager.md  # Agent definition with frontmatter
└── workflow-rules/
    └── core-orangutan.md     # Placeholder workflow rules
```

## STATE_MODEL
```python
# TEAM MEMORY state object structure
state = {
    "project_context": {
        "name": str,              # Project name
        "version": str,           # Current version (e.g., "v0.1.0.0.0.0.0.0.0.0")
        "goal": str,              # Overall project goal
        "current_task": str       # Active task being worked on
    },
    "agent_outputs": {
        "architect": {
            "summary": str,       # Last execution summary
            "artifacts": dict,    # Generated artifacts
            "next_action": str    # Recommended next action
        },
        "coder": {
            "summary": str,
            "artifacts": dict,
            "next_action": str
        },
        "devops": {
            "summary": str,
            "artifacts": dict,
            "next_action": str
        },
        "reviewer": {
            "summary": str,
            "artifacts": dict,
            "next_action": str
        },
        "release-manager": {
            "summary": str,
            "artifacts": dict,
            "next_action": str
        }
    },
    "workflow_rules": {
        "loaded_from": str,       # Path to workflow rules file
        "rules": list            # List of parsed rules (placeholder for v0.1.0.0.0.0.0.0.0.0)
    },
    "execution_history": [
        {
            "agent": str,
            "timestamp": str,
            "success": bool,
            "error": str or None
        }
    ]
}
```

## ORCHESTRATOR_DESIGN

**Responsibilities of orchestrator.py:**
- Load agent definitions from `agents/*.md` files
- Initialize and maintain the TEAM MEMORY state
- Execute agents in hardcoded v0.1.0.0.0.0.0.0.0.0 sequence: architect → coder → devops → reviewer → release-manager
- Run CLI tools as subprocesses based on agent frontmatter
- Parse structured responses and update state

**Function-level design:**

1. `main()`: Entry point, orchestrates the pipeline
2. `initialize_state()`: Creates initial TEAM MEMORY structure
3. `load_all_agents()`: Loads all agent definitions from agents/ directory
4. `run_pipeline()`: Executes the hardcoded v0.1.0.0.0.0.0.0.0.0 agent sequence
5. `execute_single_agent(agent_name, state)`: Runs one agent and updates state
6. `save_state()`: Persists state to JSON file for debugging

## IMPLEMENTATION_PLAN_FOR_CODER

### Task 1: Implement agent_loader.py
- **Files to edit:** Create `agent_loader.py`
- **Functions to implement:**
  - `load_agent(filepath)`: Parse YAML frontmatter and markdown body
  - `Agent` dataclass with fields: name, cli_command, cli_args, role_prompt
- **Acceptance criteria:** Successfully loads .md file, extracts frontmatter fields, returns Agent object

### Task 2: Implement state_manager.py
- **Files to edit:** Create `state_manager.py`
- **Functions to implement:**
  - `create_initial_state()`: Returns empty state dict with correct structure
  - `update_agent_output(state, agent_name, summary, artifacts, next_action)`: Updates state
  - `save_state_to_file(state, filepath)`: Saves as JSON
  - `load_state_from_file(filepath)`: Loads from JSON
- **Acceptance criteria:** State can be created, updated, saved, and loaded without data loss

### Task 3: Implement response_parser.py
- **Files to edit:** Create `response_parser.py`
- **Functions to implement:**
  - `parse_agent_response(stdout_text)`: Extract SUMMARY, ARTIFACTS, NEXT_ACTION sections
  - `extract_section(text, header)`: Helper to extract content under ## headers
- **Acceptance criteria:** Correctly parses multi-section markdown response into dict

### Task 4: Implement agent_executor.py
- **Files to edit:** Create `agent_executor.py`
- **Functions to implement:**
  - `execute_agent(agent, state, task)`: Main execution function
  - `build_prompt(agent, state, task)`: Constructs full prompt per spec
  - `run_subprocess(command, args, input_text)`: Wrapper for subprocess.run
- **Acceptance criteria:** Successfully runs CLI command, passes prompt via stdin, captures stdout

### Task 5: Implement orchestrator.py
- **Files to edit:** Create `orchestrator.py`
- **Functions to implement:**
  - `main()`: Entry point with hardcoded v0.1.0.0.0.0.0.0.0.0 pipeline
  - `run_v01_pipeline()`: Execute 5 agents in sequence
  - Command-line arg parsing for initial task
- **Acceptance criteria:** Full pipeline runs end-to-end with state passing between agents

## IMPLEMENTATION_PLAN_FOR_DEVOPS

### Task 1: Create directory structure
- Create all directories: `agents/`, `workflow-rules/`
- Create empty Python files per FILE_STRUCTURE

### Task 2: Create agent definition files
- Create `agents/architect.md` with frontmatter: `cli: {command: "gemini", args: []}`
- Create `agents/coder.md` with frontmatter: `cli: {command: "claude", args: []}`
- Create `agents/devops.md` with frontmatter: `cli: {command: "codex", args: []}`
- Create `agents/reviewer.md` with frontmatter: `cli: {command: "gemini", args: []}`
- Create `agents/release-manager.md` with frontmatter: `cli: {command: "claude", args: []}`
- Add role descriptions from spec to each file's body

### Task 3: Setup Python environment
- Create `requirements.txt` with: `PyYAML==6.0.1`
- Create placeholder `workflow-rules/core-orangutan.md`
- Create `.gitignore` with: `__pycache__/`, `*.pyc`, `state.json`

### Task 4: Create test harness
- Create `test_v01.sh` script that runs: `python orchestrator.py --task "Build v0.1.0.0.0.0.0.0.0.0 orchestrator"`
- Create mock CLI scripts (`mock_gemini.py`, `mock_claude.py`, `mock_codex.py`) that return valid structured responses
- These mocks read from stdin and output formatted markdown to stdout

### Task 5: Documentation
- Create `README.md` with setup instructions
- Document required CLI tools and authentication steps
- Add example of expected agent response format
