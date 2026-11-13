# Step 4 — Tree checks for `move_file` / `delete_directory`; plain move into a gitignored destination

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_4.md`), and issue #83 (Tool behaviour rows `move_file` / `delete_directory`, Decisions 7, 16, 18, 21, Constraints: Tree checks, Destination check, `move_file` error mapping).
> Implement step 4 only: tests first, then `check_tree_access`, the move-method change, and the two tool call sites.
> Run pylint, pytest (`-n auto`) and mypy; all must pass. Format, then make exactly one commit.

## WHERE

- `src/mcp_workspace/file_tools/directory_utils.py`
- `src/mcp_workspace/file_tools/file_operations.py`
- `src/mcp_workspace/toolset/move.py`, `src/mcp_workspace/toolset/delete.py`
- New: `tests/test_file_access_trees.py`

## WHAT

```python
# directory_utils.py
def _rule_access(rel: str, rules: AccessRules) -> tuple[FileAccess | None, str]: ...
def check_tree_access(src_path: str, dest_path: str | None, project_dir: Path) -> None: ...

# file_operations.py
def _determine_move_method(src_abs: Path, project_dir: Path, dest_ignored: bool) -> bool: ...
```

## HOW

- `_rule_access`: the rule / built-in part of step 2's `_access`, checked on `{rel, canonical_spelling(rel)}`; returns `(None, "")` when nothing matches. Refactor `_access` to call it, so the logic exists once.
- `check_tree_access` normalises both paths with `normalize_path`; if that raises, return and let the existing code refuse (keeps the current "Invalid path" mapping). A missing source also returns.
- `toolset/move.py`: after the two `check_writable` calls and **before the `try`**, call `check_tree_access(source_path, destination_path, ctx.project_dir)`.
- `toolset/delete.py` `delete_directory`: after `check_writable`, call `check_tree_access(dir_path, None, ctx.project_dir)`.
- `file_operations.move_file`: `dest_ignored = is_path_gitignored(dest_rel, project_dir)` (gitignore-only meaning: "never committed"), passed to `_determine_move_method`, which returns `False` first when `dest_ignored` (before the lazy GitPython import).
- Docstrings: `move_file` tool and util (refusals; gitignored destination → plain filesystem move, file ends up untracked); `delete_directory` tool Raises (any read-only file in the tree).

## ALGORITHM

```
check_tree_access(src, dest, project_dir):
    rules = load_access_rules(project_dir); files = [src_abs] if not dir else rglob files (incl. inside ignored subdirs)
    ignored = _gitignore_skip(src_abs.parent, project_dir)          # cheap per-directory predicate
    for f in files: rel = project-relative f; targets = [rel] + ([dest_rel + rel[len(src_rel):]] if dest else [])
        for t in targets: if _rule_access(t, rules)[0] is READ_ONLY: raise ValueError(f"No write access to '{t}' ({reason})")
        if dest and ignored(f) and _access(rel)[0] is HIDDEN and _access(dest_of(rel))[0] is not HIDDEN:
            raise ValueError(f"Move refused: '{src_rel}' contains files hidden by .gitignore rules that would become accessible at '{dest_rel}'")
```

The destination check uses the pre-move state (a `.gitignore` inside the moved tree is not consulted at the destination) — errs safe, as the issue accepts.

## DATA

- `check_tree_access` returns `None` or raises `ValueError`. The Decision 21 message names no hidden file.
- `_determine_move_method` → `bool` (True = `git mv`).

## Tests (`tests/test_file_access_trees.py`, write first)

Every refusal asserts the project snapshot (all file bytes, as `_snapshot` in `tests/test_file_tool_path_rules.py`) is unchanged.

- `delete_directory(recursive=True)` / `move_file` on a tree holding a file read-only by rule → refused.
- Same, with the read-only file inside an ignored subdirectory (`pkg/__pycache__/x.pyc`, rule `read-only /pkg/__pycache__/x.pyc`) → refused.
- Directory move that would create a protected file (`read-only /dst/config.json`, move `srcdir` holding `config.json` → `dst`) → refused.
- Expose via rule: `.gitignore` `.env` and `.scratch/`, rule `read-write /.scratch/`, move `src/app` (holding `.env`) → `.scratch/app` → refused; message does not contain `.env`.
- Expose via anchored gitignore, no rules file: `.gitignore` `/src/app/.env`, move `src/app` → `lib/app` → refused.
- Hidden stays hidden: `.gitignore` `__pycache__/`, move `src/a` → `src/b` → allowed, `.pyc` moved along.
- `delete_directory(".scratch", recursive=True)` under `read-write /.scratch/` with ignored files inside → allowed, everything deleted.
- Git integration (`git_integration` marker, fixtures as in `tests/file_tools/test_move_git_integration.py`): first assert a tracked file moved to a normal destination stays tracked (`method == "git"`); then a tracked file moved into gitignored `.scratch/` → `method == "filesystem"` and untracked afterwards; a directory moved into `.scratch/` also uses `"filesystem"`.
- Unit: `_determine_move_method(src, project_dir, dest_ignored=True)` is `False`.
