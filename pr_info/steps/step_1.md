# Step 1 — `server.py`: per-project default limit (global, setter, resolution, threading)

**Read `pr_info/steps/summary.md` first.** This step implements the server-side half of
issue #221: the `check_file_size` MCP tool learns a per-project default and `run_server`
learns how to receive it. This is one commit (tests + implementation + checks passing).

Follow TDD: write the tests in `tests/test_server.py` first, then implement in
`src/mcp_workspace/server.py`, then run all checks.

## WHERE

- `src/mcp_workspace/server.py`
- `tests/test_server.py` (add tests; create the file only if missing — it exists today)

## WHAT (signatures)

In `src/mcp_workspace/server.py`:

```python
# module-level, next to `_project_dir: Optional[Path] = None` (near line 44)
_file_size_limit: Optional[int] = None

@log_function_call
def set_file_size_limit(limit: Optional[int]) -> None:
    """Set the per-project default line limit used by check_file_size."""

@mcp.tool()
@log_function_call
def check_file_size(max_lines: Optional[int] = None) -> str:
    ...

@log_function_call
def run_server(
    project_dir: Path,
    reference_projects: Optional[Dict[str, ReferenceProject]] = None,
    file_size_limit: Optional[int] = None,
) -> None:
    ...
```

## HOW (integration points)

- `Optional` is already imported in `server.py` (`from typing import ... Optional`).
- `set_file_size_limit` mirrors `set_project_dir` exactly: `@log_function_call` decorator,
  `global _file_size_limit  # pylint: disable=global-statement`, assign, then
  `logger.info("File size limit set to: %s", limit)`.
- `run_server` calls `set_file_size_limit(file_size_limit)` right after
  `set_project_dir(project_dir)`. Do **not** set the global directly anywhere else.
- Update the `check_file_size` docstring so the MCP schema explains: when `max_lines` is
  omitted, the default comes from the server's `--file-size-limit` flag, falling back to
  600 if the flag was not given.
- The two downstream calls (`check_file_sizes(...)`, `render_output(...)`) receive the
  resolved int — resolve once, pass the same value to both.

## ALGORITHM (resolution inside `check_file_size`)

```
if _project_dir is None: raise ValueError("Project directory has not been set")
effective = max_lines if max_lines is not None else _file_size_limit
if effective is None: effective = 600            # explicit None test, not truthiness
allowlist = load_allowlist(_project_dir / ".large-files-allowlist")
result = check_file_sizes(_project_dir, max_lines=effective, allowlist=allowlist)
return render_output(result, effective)
```

## DATA

- `set_file_size_limit` → `None` (side effect: sets module global).
- `check_file_size` → `str` (unchanged: formatted report from `render_output`).
- `run_server` → `None` (unchanged).

## Tests (write first, `tests/test_server.py`)

Add a test class with a fixture that resets both globals so tests are isolated, e.g.:

```python
import mcp_workspace.server as server_module

@pytest.fixture(autouse=True)
def _reset_globals():
    yield
    server_module._file_size_limit = None
```

1. **Explicit `max_lines` overrides flag** — `set_project_dir(tmp_path)`,
   `set_file_size_limit(750)`; patch `mcp_workspace.server.check_file_sizes` and
   `mcp_workspace.server.render_output`; call `check_file_size(500)`; assert
   `check_file_sizes` called with `max_lines=500` and `render_output` received `500`.
2. **Flag used when omitted** — same setup, `set_file_size_limit(750)`,
   `check_file_size()`; assert resolved value is `750`.
3. **Fallback 600** — `set_file_size_limit(None)` (or leave reset), `check_file_size()`;
   assert resolved value is `600`.
4. **`run_server` threads the value** — mirror the `run_server` mock pattern used in
   `tests/test_reference_projects.py::TestReferenceProjectServerStorage` (that file, not
   this one, holds the existing `run_server` coverage): patch
   `mcp_workspace.server.mcp.run` and `mcp_workspace.server.set_file_size_limit`; call
   `run_server(Path("/test/project"), file_size_limit=750)`; assert
   `set_file_size_limit` called once with `750`. Add a second case asserting the default
   is `None` when the param is omitted.

(Patching `check_file_sizes`/`render_output` avoids touching the real filesystem; the
`render_output` mock's return value is what `check_file_size` returns — that is fine.)

## Definition of done

- New tests pass; existing tests still pass.
- Run all checks and fix any issue before committing:
  - `mcp__mcp-tools-py__run_pylint_check`
  - `mcp__mcp-tools-py__run_pytest_check` with
    `extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]`
  - `mcp__mcp-tools-py__run_mypy_check`
- `set_file_size_limit` is called by `run_server` in this same commit, so vulture sees it
  as used.
- Exactly one commit for this step (run `./tools/format_all.sh` before committing).
