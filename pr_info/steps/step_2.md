# Step 2 — MCP tool + docstring cleanup + server tests

**One commit.** Depends on Step 1 (the util must exist). TDD: write server tests
first, then register the tool, then make checks pass.

## WHERE

- `src/mcp_workspace/server.py` — import the util, register the `@mcp.tool()`,
  tighten two neighbouring docstrings.
- `tests/test_server.py` — add gitignore / boundary server tests.
- `vulture_whitelist.py` — add `_.delete_directory` **only if** vulture flags the
  new tool function as unused (mirrors the existing `_.delete_this_file` entry).

## WHAT

```python
@mcp.tool()
@log_function_call
def delete_directory(dir_path: str, recursive: bool = False) -> list[str]:
    """Delete a directory from the filesystem.

    Handles directories only — for files use delete_this_file. Deletes an empty
    directory by default; pass recursive=True to delete a non-empty tree. Missing
    directory is a no-op (returns a message, no error).
    """
```

## HOW (integration)

- Import near the other util imports (server.py ~line 19):
  `from mcp_workspace.file_tools import delete_directory as delete_directory_util`
- Mirror `delete_this_file` (server.py:326): validate `dir_path` is non-empty
  `str` → check `_project_dir is not None` → `_check_not_gitignored(dir_path)` →
  delegate to `delete_directory_util(dir_path, project_dir=_project_dir, recursive=recursive)`
  inside a try/except that logs and re-raises.
- **Docstring cleanup (bundled, same commit):**
  - `save_file` (server.py:244) — add a line noting it **auto-creates parent
    directories**.
  - `delete_this_file` (server.py:326) — add a line noting it handles **files
    only, not directories** (cross-reference `delete_directory`).
  - `delete_directory` docstring cross-references `delete_this_file`.

## ALGORITHM (server wrapper)

```
if not dir_path or not isinstance(dir_path, str): raise ValueError(non-empty string)
if _project_dir is None: raise ValueError("Project directory has not been set")
_check_not_gitignored(dir_path)                       # top-level guard only
try: return delete_directory_util(dir_path, project_dir=_project_dir, recursive=recursive)
except Exception: log and re-raise
```

## DATA

- Returns `list[str]` (same contract as the util — see summary).
- Raises `ValueError` when gitignored (top-level), project dir unset, or invalid
  input; propagates the util's `ValueError`s (outside-dir, root, path-is-file,
  non-empty-without-recursive).

## Tests to add (`tests/test_server.py`)

Use the existing `gitignore_project` fixture (blocks `*.log` and `__pycache__/`).
Import `delete_directory` from `mcp_workspace.server`. Add near
`test_delete_file_gitignored`:

1. `test_delete_directory_gitignored` — create a `*.log`-matching dir (e.g.
   `logs.log/`) or a dir whose name is gitignored; expect `ValueError` matching
   `excluded by .gitignore`. (Simplest: gitignore blocks `__pycache__/`; create
   top-level `__pycache__/` and assert `delete_directory("__pycache__")` raises.)
2. `test_delete_directory_recursive_deletes_gitignored_children` — create a
   non-ignored dir `build/` containing a nested `build/__pycache__/x.pyc`;
   `delete_directory("build", recursive=True)` succeeds and removes the whole
   tree including the gitignored child; `build/` is gone.

## Checks (mandatory, after edits)

```
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check   # extra_args=["-n","auto","-m","not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]
mcp__mcp-tools-py__run_mypy_check
```

If vulture is run in CI and flags `delete_directory`, add `_.delete_directory` to
`vulture_whitelist.py`.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Implement Step 2
> only: register the `delete_directory` MCP tool in
> `src/mcp_workspace/server.py` (thin wrapper over the Step-1 util, enforcing
> `_check_not_gitignored`), tighten the `save_file` and `delete_this_file`
> docstrings as described, and add the listed server tests to
> `tests/test_server.py`. Follow TDD (tests first). Use only MCP workspace tools
> for file edits. After each edit run pylint, pytest (fast-unit exclusion
> markers), and mypy; fix everything until all pass. If vulture flags the new
> tool, add `_.delete_directory` to `vulture_whitelist.py`. Do not touch
> `README.md` — that is Step 3. Produce exactly one commit's worth of change.
