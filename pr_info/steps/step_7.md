# Step 7 — Commit reporting: `committed_files`, public `format_dirty_tree`

## LLM prompt

> Read `pr_info/steps/summary.md` (design point 9) and this file. Implement step 7 only:
> tests first, then `committed_files` and the rename. Run format, pylint, pytest (`-n auto`),
> mypy, lint-imports and ruff; all must pass. Make exactly one commit.

## WHERE

- `src/mcp_workspace/git_operations/commits.py`: new `committed_files`.
- `src/mcp_workspace/git_operations/remotes.py`: rename `_format_dirty_tree` → `format_dirty_tree`
  (use `mcp__mcp-tools-py__rename_symbol`; updates the caller in `rebase_onto_branch` and
  `tests/git_operations/test_remotes.py`). Behaviour unchanged.
- New tests: `tests/git_operations/test_commit_reporting.py`

Neither is exported from `__init__.py`.

## WHAT

```python
def committed_files(project_dir: Path, rev: str = "HEAD") -> list[str]: ...
def format_dirty_tree(project_dir: Path) -> str: ...      # renamed only
```

## HOW

`committed_files`: `run_git_raw(repo, "diff_tree", "--root", "--no-commit-id", "--name-only",
"-r", "-z", rev)` inside `safe_repo_context`; failure or non-repo → `[]`.

## ALGORITHM

```
if is_option_like(rev): []
rc, out, _ = run_git_raw(...); rc != 0 -> []
return [p for p in out.decode("utf-8", "replace").split("\0") if p]
```

## DATA

`list[str]` of repo-relative paths changed by `rev` (added, modified, deleted).

## Tests (write first)

Integration (`git_integration`):
- root commit with two files → both listed.
- commit adding one, modifying one, deleting one → all three listed.
- non-repository → `[]`.

Existing `_format_dirty_tree` tests keep passing under the new name.

## Commit

`feat(git_operations): add committed_files; make format_dirty_tree public`
