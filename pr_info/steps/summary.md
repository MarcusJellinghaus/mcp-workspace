# Issue #50 — Add `delete_directory` tool — Implementation Summary

## Goal

Add a `delete_directory` tool (util layer + MCP layer) so callers can delete
directories through MCP instead of falling back to `rm -rf` via bash. Scope is
**delete-only** — no `mkdir`/`create_directory` (out of scope: `save_file` and
`move_file` already auto-create parent dirs, and git can't track empty dirs).

## Architectural / design changes

- **No new modules or folders.** The feature mirrors the existing
  `delete_file` / `delete_this_file` split across the two established layers:
  - **Util layer** (`file_tools/file_operations.py`): pure filesystem logic,
    boundary validation via `normalize_path`, no git, no gitignore. Directly
    unit-tested.
  - **MCP layer** (`server.py`): thin `@mcp.tool()` wrapper that enforces the
    `_check_not_gitignored()` security boundary (top-level path only) and
    delegates to the util.
- **Plain filesystem, no git awareness** — consistent with `delete_this_file`
  (`unlink()`), deliberately *not* copying `move_file`'s git-mv behavior.
- **New guard not present in the file tools: project-root refusal.**
  `normalize_path(".", project_dir)` resolves to the repo root, and
  `recursive=True` would turn that into `shutil.rmtree(project_root)` — wiping
  the repo incl. `.git`. The util refuses when the normalized target resolves to
  `project_dir`.
- **Idempotent delete** — a missing directory is not an error (returns a
  "does not exist" message), unlike `delete_file` which raises `FileNotFoundError`.
  This is intentional for the test-teardown use case.
- **Recursive delete removes gitignored *children* by design** — only the
  top-level `dir_path` passes through `_check_not_gitignored`; `shutil.rmtree`
  then removes the whole tree (e.g. nested `__pycache__/`, `.env`). Conscious
  departure from the per-path-guarded file tools.
- **Return contract change vs. `delete_file`** — returns `list[str]` of every
  deleted path (target + intermediate dirs + files), capped at 20 with a summary
  line as entry #21, rather than a bare `bool`.
- **Bundled docstring cleanup** clarifies the file-vs-directory boundary on the
  neighbouring MCP tools.

## Util signature

```python
def delete_directory(
    dir_path: str, project_dir: Path, recursive: bool = False
) -> list[str]: ...
```

## MCP signature

```python
@mcp.tool()
@log_function_call
def delete_directory(dir_path: str, recursive: bool = False) -> list[str]: ...
```

## Behavior table (requirements)

| Situation | Behavior |
|-----------|----------|
| Empty dir, `recursive=False` | Delete via `Path.rmdir()`. Return `[dir_path]`. |
| Non-empty dir, `recursive=False` | Raise `ValueError` — instruct caller to pass `recursive=True`. |
| Any dir, `recursive=True` | Delete tree via `shutil.rmtree()`. |
| Path is a **file** | Raise `ValueError`: `"Path 'X' is a file, not a directory. Use delete_this_file instead."` |
| Path is **project root** | Raise `ValueError` — refuse (would wipe repo + `.git`). |
| Path **does not exist** | Idempotent — return `["Directory 'X' does not exist — nothing to delete"]`. |
| Path **gitignored** (top-level) | Raise `ValueError` (excluded by .gitignore) — enforced at MCP layer. |
| Path **outside project dir** | Raise `ValueError` — via `normalize_path`. |
| Gitignored **children** (recursive) | Deleted by design — only top-level dir is guard-checked. |

## Return value

`list[str]` of every deleted path (relative to project dir): target dir + all
intermediate dirs + all files. **Capped at 20 entries**; if more were deleted,
entry #21 is a summary line, e.g.
`"... and 34 more (42 files, 6 dirs deleted total)"`. For ≤ 20 entries, the plain
list with no summary line. Paths are `sorted()` for deterministic output.

## Core algorithm (util)

```
validate dir_path (non-empty str), project_dir (not None)
abs_path, rel_path = normalize_path(dir_path, project_dir)     # ValueError if outside
if abs_path.resolve() == project_dir.resolve(): raise ValueError  # root guard
if not abs_path.exists(): return ["Directory '<rel>' does not exist — nothing to delete"]
if abs_path.is_file(): raise ValueError("... Use delete_this_file instead.")
children = sorted(abs_path.rglob("*"))
if children and not recursive: raise ValueError("... pass recursive=True")
n_files = count files in children; n_dirs = count dirs in children + 1  # pre-delete!
all_rel = [rel_path] + [child relative-to project_dir for each child]
shutil.rmtree(abs_path) if recursive else abs_path.rmdir()
return _format_deleted_paths(all_rel, n_files, n_dirs)          # cap at 20 + summary
```

Counts and the path list are collected from a **single** `rglob("*")` walk
**before** deleting (paths vanish after `rmtree`), so the returned list reflects
*intended* deletions.

## Files created / modified

**No new folders or modules.** Modified files:

| File | Change | Step |
|------|--------|------|
| `src/mcp_workspace/file_tools/file_operations.py` | Add `delete_directory()` + `_format_deleted_paths()` helper | 1 |
| `src/mcp_workspace/file_tools/__init__.py` | Export `delete_directory` (import block + `__all__`) | 1 |
| `tests/file_tools/test_file_operations.py` | Util test cases | 1 |
| `src/mcp_workspace/server.py` | Import + `@mcp.tool()` `delete_directory`; tighten `save_file` & `delete_this_file` docstrings | 2 |
| `tests/test_server.py` | Server-layer gitignore tests | 2 |
| `vulture_whitelist.py` | Add `_.delete_directory` if vulture flags the tool | 2 |
| `README.md` | Features bullet, tools table row, `delete_directory` detail section | 3 |

## Steps (one commit each)

1. **Util + unit tests** — `delete_directory()` in `file_operations.py`, export, tests.
2. **MCP tool + docstring cleanup + server tests** — registration, gitignore
   enforcement, `save_file`/`delete_this_file` docstring notes.
3. **README docs** — features list, tools table, detail section.

## Constraints preserved

- No `mkdir` / `create_directory`.
- No git awareness (plain `shutil`/`Path`).
- gitignore guard kept at MCP layer (top-level only).
- Project-root refusal.
- KISS: single tree walk, one small formatting helper, shared code path for the
  empty and recursive branches (only the delete call differs).
