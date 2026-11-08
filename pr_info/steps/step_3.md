# Step 3 — `read_reference_file` passes the configured limit

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 3** exactly as described in `pr_info/steps/step_3.md`. Write/update the tests first, then the implementation. Run pylint, pytest (`-n auto`) and mypy via the MCP tools; all must pass. Run `run_format_code`, then make one commit.

## Precondition

Step 1 is done (`DEFAULT_READ_MAX_LINES` importable from `mcp_workspace.file_tools`, `read_file` accepts `max_lines`). If not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/server_reference_tools.py`
- `tests/test_reference_projects_mcp_tools.py`

## WHAT

```python
from mcp_workspace.file_tools import DEFAULT_READ_MAX_LINES

_read_max_lines: int | None = DEFAULT_READ_MAX_LINES

@log_function_call
def set_reference_read_max_lines(limit: int | None) -> None:
    """Set the full-read line limit used by read_reference_file."""
```

`read_reference_file` — signature unchanged; adds `max_lines=_read_max_lines` to the `read_file_util(...)` call.

## HOW

- Setter mirrors `set_reference_projects` (`global _read_max_lines  # pylint: disable=global-statement`, `logger.info("Reference read max lines set to: %s", limit)`).
- Named `set_reference_read_max_lines` (not `set_read_max_lines`) to avoid a name clash in `server.py`, which imports from this module.
- Docstring of `read_reference_file`: add that full reads beyond the configured limit (default 2000 lines) are cut, with a note giving the next `start_line` / `end_line`; explicit ranges are returned in full.

## ALGORITHM

None beyond passing the module value through.

## DATA

No change to return type.

## Tests (write first) — `tests/test_reference_projects_mcp_tools.py`

- Update the exact-kwargs assertions (~lines 279-285 and 318-324) to include `max_lines=DEFAULT_READ_MAX_LINES` (or the value set via the setter — reset module state in the test to avoid leaking).
- New: after `set_reference_read_max_lines(3)`, `read_reference_file` on a real 5-line file in a `tmp_path` reference project (patch `ensure_available`) returns 3 lines + the truncation note. Restore the default afterwards (e.g. `monkeypatch.setattr` on `_read_max_lines`, or call the setter with `DEFAULT_READ_MAX_LINES` in teardown).
- New: setter round trip (`set_reference_read_max_lines(42)` → module `_read_max_lines == 42`).
