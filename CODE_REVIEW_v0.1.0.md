# Code Review: Multi-CLI Agent Orchestrator v0.1.0

## SUMMARY

- Overall implementation is clean, focused, and achieves v0.1.0 goals effectively
- Code follows good Python practices with proper error handling and logging
- Some minor improvements needed around error resilience and subprocess security
- GitHub Actions workflow is minimal but functional
- Makefile structure follows conventions well

## ISSUES

### [ISSUE-1] Subprocess execution lacks timeout protection
- **Type:** bug / security
- **Location:** orchestrator.py, execute_single_agent function
- **Details:** subprocess.run() has no timeout, allowing agents to hang indefinitely and block the pipeline. This could be exploited or cause CI/CD failures.
- **Suggested fix:** Add a configurable timeout parameter (default 300 seconds) to prevent runaway processes

### [ISSUE-2] Shell injection vulnerability in subprocess command
- **Type:** security
- **Location:** orchestrator.py, execute_single_agent function
- **Details:** While currently using list-based subprocess commands (safe), there's no validation that cli_command and cli_args don't contain shell metacharacters if they come from untrusted sources
- **Suggested fix:** Add validation to ensure cli_command is a simple executable name/path without shell operators

### [ISSUE-3] Missing error recovery for malformed agent outputs
- **Type:** bug
- **Location:** orchestrator.py, execute_single_agent function
- **Details:** If an agent returns non-UTF8 data or extremely large output, the current text=True mode could fail or consume excessive memory
- **Suggested fix:** Add output size limits and handle encoding errors gracefully

### [ISSUE-4] State file overwrite without backup
- **Type:** design
- **Location:** orchestrator.py, save_state function
- **Details:** Direct overwrite of state.json could lose data if write fails midway. No atomic write or backup mechanism.
- **Suggested fix:** Write to temporary file first, then atomic rename

### [ISSUE-5] Hardcoded pipeline sequence reduces flexibility
- **Type:** design
- **Location:** orchestrator.py, run_v01_pipeline function
- **Details:** Pipeline order is hardcoded in function rather than configuration, making it harder to modify or test different sequences
- **Suggested fix:** Move pipeline sequence to a constant or configuration parameter

## PROPOSED_PATCHES

### PATCH 1: Add timeout protection to agent execution

**File:** orchestrator.py  
**Function:** execute_single_agent

```python
def execute_single_agent(
    agent: Agent, 
    state: Dict[str, Any], 
    task: str,
    timeout: int = 300  # 5 minutes default
) -> None:
    """
    Execute one agent via subprocess and update TEAM MEMORY.
    
    Args:
        agent: Agent to execute
        state: Current TEAM MEMORY state
        task: Task description
        timeout: Maximum execution time in seconds
    """
    payload = {
        "agent_name": agent.name,
        "role_prompt": agent.role_prompt,
        "task": task,
        "state": state,
        "workflow_rules": agent.workflow_rules,
    }
    input_text = json.dumps(payload, indent=2)

    cmd = [agent.cli_command] + agent.cli_args
    started_at = datetime.utcnow().isoformat() + "Z"

    try:
        completed = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,  # Add timeout protection
        )
        success = completed.returncode == 0
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
    except subprocess.TimeoutExpired:
        success = False
        stdout = ""
        stderr = f"Agent execution timed out after {timeout} seconds"
    except FileNotFoundError as exc:
        success = False
        stdout = ""
        stderr = f"Failed to execute agent command: {exc}"
    except Exception as exc:  # Catch other subprocess errors
        success = False
        stdout = ""
        stderr = f"Unexpected error executing agent: {exc}"

    separator = "=" * 80
    print(separator)
    print(f"[orchestrator] Agent: {agent.name}")
    print(f"[orchestrator] Command: {' '.join(cmd)}")
    print(f"[orchestrator] Success: {success}")
    if stdout:
        print(f"[orchestrator] STDOUT:\n{stdout}")
    if stderr:
        print(f"[orchestrator] STDERR:\n{stderr}", file=sys.stderr)

    # Minimal state update: store raw output as summary
    state["agent_outputs"][agent.name] = {
        "summary": stdout,
        "artifacts": {},    # Reserved for future structured parsing
        "next_action": "",  # Reserved for future NEXT_ACTION parsing
    }

    # Append execution history entry
    state["execution_history"].append(
        {
            "agent": agent.name,
            "timestamp": started_at,
            "success": success,
            "error": None if success else (stderr or "Unknown error"),
        }
    )
```

### PATCH 2: Add command validation for security

**File:** orchestrator.py  
**Functions:** validate_agent_command (new) and load_agent (modified)

```python
def validate_agent_command(agent: Agent) -> None:
    """
    Validate agent command for security issues.
    
    Raises:
        ValueError: If command contains potentially dangerous characters
    """
    # Check for shell metacharacters in command
    dangerous_chars = set(';|&$`(){}[]<>*?~')
    if any(char in agent.cli_command for char in dangerous_chars):
        raise ValueError(
            f"Agent '{agent.name}' has potentially dangerous characters in cli_command: {agent.cli_command}"
        )
    
    # Check args as well
    for arg in agent.cli_args:
        if any(char in arg for char in dangerous_chars):
            raise ValueError(
                f"Agent '{agent.name}' has potentially dangerous characters in cli_args: {arg}"
            )

def load_agent(path: str) -> Agent:
    """Load a single agent .md file into an Agent object."""
    frontmatter, body = parse_frontmatter_and_body(path)

    name = frontmatter.get("name") or os.path.splitext(os.path.basename(path))[0]
    cli_command = frontmatter.get("cli_command")
    if not cli_command:
        raise ValueError(f"Agent '{name}' missing 'cli_command' in {path}")

    cli_args = frontmatter.get("cli_args") or []
    if not isinstance(cli_args, list):
        raise TypeError(f"'cli_args' for agent '{name}' must be a list")

    role_prompt = frontmatter.get("role_prompt") or body or ""
    workflow_rules = frontmatter.get("workflow_rules") or []
    if isinstance(workflow_rules, str):
        workflow_rules = [workflow_rules]

    agent = Agent(
        name=name,
        cli_command=cli_command,
        cli_args=cli_args,
        role_prompt=role_prompt.strip(),
        workflow_rules=workflow_rules,
    )
    
    # Validate before returning
    validate_agent_command(agent)
    return agent
```

### PATCH 3: Implement atomic state file writes

**File:** orchestrator.py  
**Function:** save_state

```python
import tempfile  # Add to imports at top of file

def save_state(state: Dict[str, Any], path: str) -> None:
    """Persist TEAM MEMORY state to a JSON file atomically."""
    # Write to temporary file in same directory (for atomic rename)
    dir_path = os.path.dirname(path) or "."
    
    with tempfile.NamedTemporaryFile(
        mode='w',
        dir=dir_path,
        prefix='.tmp_state_',
        suffix='.json',
        delete=False,
        encoding='utf-8'
    ) as tmp_file:
        json.dump(state, tmp_file, indent=2)
        tmp_path = tmp_file.name
    
    # Atomic rename (on POSIX systems)
    try:
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file if rename fails
        os.unlink(tmp_path)
        raise
```

### PATCH 4: Make pipeline sequence configurable

**File:** orchestrator.py  
**Add constant and modify run_v01_pipeline**

```python
# Add at module level after imports
DEFAULT_PIPELINE = [
    "analyst",
    "architect", 
    "coder",
    "devops",
    "reviewer",
    "release-manager",
]

def run_v01_pipeline(
    agents: Dict[str, Agent], 
    state: Dict[str, Any], 
    task: str,
    pipeline: Optional[List[str]] = None,
    timeout: int = 300
) -> None:
    """
    Run the v0.1.0 pipeline.
    
    Args:
        agents: Available agents
        state: TEAM MEMORY state
        task: Task description
        pipeline: Agent execution sequence (uses DEFAULT_PIPELINE if None)
        timeout: Per-agent execution timeout in seconds
    """
    if pipeline is None:
        pipeline = DEFAULT_PIPELINE
    
    for name in pipeline:
        agent = agents.get(name)
        if not agent:
            print(
                f"[orchestrator] WARNING: Agent '{name}' not found; skipping",
                file=sys.stderr,
            )
            continue
        execute_single_agent(agent, state, task, timeout=timeout)
```

### PATCH 5: Add timeout CLI argument

**File:** orchestrator.py  
**Functions:** parse_args and main

```python
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="v0.1.0 multi-CLI agent orchestrator",
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Natural language description of the task for the agent team.",
    )
    parser.add_argument(
        "--agents-dir",
        default="agents",
        help="Directory containing agent .md definitions.",
    )
    parser.add_argument(
        "--workflow-rules",
        default="workflow-rules/core-orangutan.md",
        help="Path to core workflow rules file (orangutan).",
    )
    parser.add_argument(
        "--state-path",
        default="state.json",
        help="Path to write final TEAM MEMORY state as JSON.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Per-agent execution timeout in seconds (default: 300).",
    )
    return parser.parse_args(argv)

def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    try:
        agents = load_all_agents(args.agents_dir)
    except Exception as exc:  # noqa: BLE001 (simple top-level error handling)
        print(f"[orchestrator] ERROR: {exc}", file=sys.stderr)
        return 1

    if not agents:
        print(
            f"[orchestrator] ERROR: No agents loaded from {args.agents_dir}",
            file=sys.stderr,
        )
        return 1

    state = initialize_state(args.task, args.workflow_rules)
    run_v01_pipeline(agents, state, args.task, timeout=args.timeout)
    save_state(state, args.state_path)
    print(f"[orchestrator] Saved TEAM MEMORY state to {args.state_path}")
    return 0
```

## Implementation Priority

1. **HIGH PRIORITY (Security/Stability):**
   - PATCH 1: Timeout protection
   - PATCH 2: Command validation
   - PATCH 3: Atomic file writes

2. **MEDIUM PRIORITY (Flexibility):**
   - PATCH 4: Configurable pipeline
   - PATCH 5: CLI timeout argument

3. **FUTURE CONSIDERATIONS:**
   - Add output size limits (mentioned in ISSUE-3)
   - Implement structured output parsing (SUMMARY/ARTIFACTS/NEXT_ACTION)
   - Add retry mechanism for transient failures
   - Implement parallel agent execution where applicable

## Testing Recommendations

After applying these patches:

1. **Unit Tests:** Add tests for validate_agent_command function
2. **Integration Tests:** Test timeout behavior with a mock long-running agent
3. **Security Tests:** Verify rejection of malicious agent commands
4. **Stress Tests:** Test with large outputs and multiple concurrent runs
5. **CI/CD:** Update GitHub Actions to test with various timeout values

## Conclusion

The v0.1.0 implementation provides a solid foundation. These patches address the most critical issues while maintaining the simplicity and clarity of the original design. After applying these fixes, the system will be more robust, secure, and ready for production use as a v0.1.0 release.
