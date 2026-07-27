# Step 1 — Util layer: `delete_directory()` + unit tests

**One commit.** TDD: write the tests first, then the implementation, then make
all checks pass.

## WHERE

- `src/mcp_workspace/file_tools/file_operations.py` — add `delete_directory()`
  and a private `_format_deleted_paths()` helper.
- `src/mcp_workspace/file_tools/__init__.py` — export `delete_directory`.
- `tests/file_tools/test_file_operations.py` — add util test cases.

## WHAT

```python
def delete_directory(
    dir_path: str, project_dir: Path, recursive: bool = False
) -> list[str]:
    """Delete a directory (empty by default, whole tree with recursive=True).

    Plain filesystem — no git. Files-only tool is delete_file. Handles
    directories only. Missing directory is idempotent (no error).
    """


def _format_deleted_paths(
    paths: list[str], n_files: int, n_dirs: int
) -> list[str]:
    """Cap the deleted-path list at 20, appending a summary line as entry #21."""
```

`shutil` and `Path` are already imported in `file_operations.py`; no new imports
needed beyond the existing `normalize_path`.

## HOW (integration)

- Reuse `normalize_path(dir_path, project_dir)` for boundary validation — the
  same call `delete_file` uses.
- Mirror `delete_file`'s parameter-validation preamble (non-empty `str`,
  `project_dir` not None).
- Add `delete_directory` to the `from ...file_operations import (...)` block and
  to `__all__` in `file_tools/__init__.py`, alongside `delete_file`.

## ALGORITHM (`delete_directory`)

```
validate dir_path is non-empty str; project_dir is not None
abs_path, rel_path = normalize_path(dir_path, project_dir)      # ValueError if outside
if abs_path.resolve() == project_dir.resolve(): raise ValueError(refuse project root)
if not abs_path.exists(): return [f"Directory '{rel_path}' does not exist — nothing to delete"]
if abs_path.is_file(): raise ValueError(f"Path '{rel_path}' is a file, not a directory. Use delete_this_file instead.")
children = sorted(abs_path.rglob("*"))
if children and not recursive: raise ValueError(f"Directory '{rel_path}' is not empty. Pass recursive=True to delete it and its contents.")
n_files = sum(1 for p in children if p.is_file()); n_dirs = sum(1 for p in children if p.is_dir()) + 1
all_rel = [rel_path] + [str(p.relative_to(project_dir)) for p in children]
shutil.rmtree(abs_path) if recursive else abs_path.rmdir()
return _format_deleted_paths(all_rel, n_files, n_dirs)
```

## ALGORITHM (`_format_deleted_paths`)

```
if len(paths) <= 20: return paths
return paths[:20] + [f"... and {len(paths) - 20} more ({n_files} files, {n_dirs} dirs deleted total)"]
```

Counts and the path list come from a **single** `rglob("*")` walk collected
**before** deleting (paths vanish after `rmtree`). `n_dirs` adds 1 for the target
dir itself; `len(all_rel) == n_files + n_dirs`.

## DATA

- Returns `list[str]` of paths relative to `project_dir`, sorted, capped at 20
  with a summary line as entry #21 when truncated.
- Empty-dir success returns `[rel_path]` (single entry).
- Missing dir returns `["Directory '<rel>' does not exist — nothing to delete"]`.
- Raises `ValueError` for: invalid `dir_path`, `None` project_dir, outside
  project dir, project root, path-is-a-file, non-empty without `recursive`.

## Tests to add (`tests/file_tools/test_file_operations.py`)

Import `delete_directory` from `mcp_workspace.file_tools.file_operations`. Use the
existing `project_dir` fixture. Add:

1. `test_delete_directory_empty` — create empty dir; `recursive=False`; returns
   `[rel]`; dir gone.
2. `test_delete_directory_non_empty_without_recursive_raises` — dir with a file;
   `recursive=False` raises `ValueError` matching `recursive=True`; dir still exists.
3. `test_delete_directory_recursive` — nested tree (dirs + files);
   `recursive=True`; dir gone; returned list contains the target, subdirs, files.
4. `test_delete_directory_path_is_file_raises` — create a file; expect
   `ValueError` matching `delete_this_file`.
5. `test_delete_directory_project_root_refused` — call with `"."`; expect
   `ValueError`; `project_dir` still exists.
6. `test_delete_directory_not_found_idempotent` — non-existent path; returns
   single-entry list containing `does not exist`; no exception.
7. `test_delete_directory_outside_project_raises` — `"../evil"`; `ValueError`
   with `Security error`.
8. `test_delete_directory_truncation_summary` — create 25 files in a dir;
   `recursive=True`; result length is 21; entry #21 startswith `... and 6 more`
   (25 files + the prepended target dir = 26 returned paths; 26 − 20 = 6)
   and contains `dirs deleted total`.

## Checks (mandatory, after edits)

```
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check   # extra_args=["-n","auto","-m","not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]
mcp__mcp-tools-py__run_mypy_check
```

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Implement Step 1
> only: add the `delete_directory()` util and `_format_deleted_paths()` helper to
> `src/mcp_workspace/file_tools/file_operations.py`, export `delete_directory`
> from `src/mcp_workspace/file_tools/__init__.py`, and add the listed unit tests
> to `tests/file_tools/test_file_operations.py`. Follow TDD (tests first). Use
> only MCP workspace tools for file edits. After each edit run pylint, pytest
> (with the fast-unit exclusion markers), and mypy; fix everything until all pass.
> Do not touch `server.py` or `README.md` — those are later steps. Produce exactly
> one commit's worth of change.
