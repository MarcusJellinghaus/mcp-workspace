# Step 4 — `server.py`: `read_file` passes the limit; `run_server(read_max_lines=...)`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 4** exactly as described in `pr_info/steps/step_4.md`. Write/update the tests first, then the implementation. Run pylint, pytest (`-n auto`) and mypy via the MCP tools; all must pass. Run `run_format_code`, then make one commit.

## Precondition

Steps 1 and 3 are done (`DEFAULT_READ_MAX_LINES` exported; `set_reference_read_max_lines` exists in `server_reference_tools.py`). If not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/server.py`
- `tests/test_server.py`

## WHAT

```python
# next to _file_size_limit
_read_max_lines: int | None = DEFAULT_READ_MAX_LINES

@log_function_call
def set_read_max_lines(limit: int | None) -> None:
    """Set the full-read line limit used by read_file."""

def run_server(
    project_dir: Path,
    reference_projects: dict[str, ReferenceProject] | None = None,
    file_size_limit: int | None = None,
    fail_on_reviews: bool = False,
    enforce_base_branch_format: bool = True,
    read_max_lines: int | None = DEFAULT_READ_MAX_LINES,
) -> None: ...
```

## HOW

- Import `DEFAULT_READ_MAX_LINES` from `mcp_workspace.file_tools` (alongside the existing `read_file_util` import) and `set_reference_read_max_lines` from `mcp_workspace.server_reference_tools` (alongside `set_reference_projects`).
- `set_read_max_lines` placed directly after `set_file_size_limit`, same shape (`global`, `logger.info("Read max lines set to: %s", limit)`).
- `read_file` tool wrapper: add `max_lines=_read_max_lines` to the `read_file_util(...)` call; signature unchanged.
- `run_server`: after `set_file_size_limit(...)`, call `set_read_max_lines(read_max_lines)` and `set_reference_read_max_lines(read_max_lines)` — unconditionally, **not** inside `if reference_projects:`. Add the arg to the docstring.
- `read_file` docstring: full reads beyond the configured limit (default 2000 lines) are cut with a note giving the next `start_line` / `end_line`; explicit ranges are returned in full.

## ALGORITHM

None beyond passing values through.

## DATA

No change to return types.

## Tests (write first) — `tests/test_server.py`

- Update the exact-kwargs assertion in `test_read_file_forwards_line_range_params` (~lines 403-409) to include `max_lines=DEFAULT_READ_MAX_LINES`.
- New: with `_read_max_lines` monkeypatched to `3`, `read_file` on a real 5-line file returns 3 lines + truncation note.
- New: `run_server(project_dir, read_max_lines=7)` with `mcp.run` patched → `server._read_max_lines == 7` and `server_reference_tools._read_max_lines == 7`, with no reference projects given. Restore both module values afterwards (monkeypatch).
- New: `run_server(project_dir)` with `mcp.run` patched → both equal `DEFAULT_READ_MAX_LINES`.
