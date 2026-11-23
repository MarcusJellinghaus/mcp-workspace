# Step 9 — `reference_fetch_interval_minutes` setting (tool_specs, server, CLI)

The value is stored but not used yet (step 10 uses it).

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_9.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy and vulture; all must pass.
> Run `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/reference_projects.py` — constant
- `src/mcp_workspace/toolset/_context.py`, `src/mcp_workspace/toolset/__init__.py`
- `src/mcp_workspace/server.py` — `run_server`
- `src/mcp_workspace/main.py`
- `tests/toolset/test_toolset.py`, `tests/test_server.py`, `tests/test_main.py`

## WHAT

```python
# reference_projects.py
DEFAULT_REFERENCE_FETCH_INTERVAL_MINUTES = 15

# toolset/_context.py — WorkspaceContext, after enforce_base_branch_format
reference_fetch_interval_minutes: int = DEFAULT_REFERENCE_FETCH_INTERVAL_MINUTES

# toolset/__init__.py
def tool_specs(project_dir, *, ..., enforce_base_branch_format: bool = True,
               reference_fetch_interval_minutes: int = DEFAULT_REFERENCE_FETCH_INTERVAL_MINUTES
               ) -> tuple[ToolSpec, ...]:
    if reference_fetch_interval_minutes < 0:
        raise ValueError(f"reference_fetch_interval_minutes must be >= 0, got {reference_fetch_interval_minutes}")

# server.py
def run_server(project_dir, ..., read_max_lines=DEFAULT_READ_MAX_LINES,
               reference_fetch_interval_minutes: int = DEFAULT_REFERENCE_FETCH_INTERVAL_MINUTES) -> None
```

## HOW

- `tool_specs` passes the value into `WorkspaceContext(...)` by keyword; docstring Args
  entry: "Minutes between automatic fetches of a reference project before it is read;
  0 turns auto-fetch off."
- `run_server` logs it with the other settings and forwards it to `create_server(...)`
  (which forwards `**settings` to `tool_specs` unchanged).
- `main.py`:
  - `parser.add_argument("--reference-fetch-interval-minutes", type=int,
    default=DEFAULT_REFERENCE_FETCH_INTERVAL_MINUTES, help=...)` next to
    `--reference-project`; help: "Minutes between automatic `git fetch origin` of a
    reference project before it is read (0 = off; defaults to 15)."
  - Validation next to `--read-max-lines`: negative →
    `ValueError("--reference-fetch-interval-minutes must be a non-negative integer: N")`.
  - `run_server(..., reference_fetch_interval_minutes=args.reference_fetch_interval_minutes)`
    — passed straight through. Never `value or DEFAULT_…`: that turns `0` (off) into 15.
  - While here, fix the `--reference-project` help / usage text if it still shows the old
    `NAME=/path` format (the help in `main.py` already shows `name=…,path=…`; check the
    module docstring / usage line).

## Tests (write first)

- `tool_specs(tmp, reference_fetch_interval_minutes=-1)` raises `ValueError`;
  `0` and `5` are accepted, and the value reaches the context (e.g. inspect via a tool
  closure or by patching `WorkspaceContext`).
- Default is 15.
- `tests/test_server.py`: `run_server(..., reference_fetch_interval_minutes=7)` forwards 7
  to `create_server` / `tool_specs` (follow the existing `read_max_lines` forwarding test).
- `tests/test_main.py`: the flag parses; a negative value fails at startup with the message
  above; when omitted, `run_server` receives 15; `--reference-fetch-interval-minutes 0`
  reaches `run_server` as `0` (not 15) (follow the existing `--read-max-lines` tests).
