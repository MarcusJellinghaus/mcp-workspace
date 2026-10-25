# Step 17 — `has_staged_changes`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 17 only, tests first, in
`repository_status.py`. Run the checks from the summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/repository_status.py`
- `src/mcp_workspace/git_operations/__init__.py` (export; count +1)
- `tests/git_operations/test_working_tree_status.py`

## WHAT
```python
def has_staged_changes(project_dir: Path) -> bool:
    """True if the index differs from HEAD (or from the empty tree on an unborn HEAD)."""
```

## HOW
Plain-value query: `open_repo_for_query` (non-repo → `ValueError`); any exit code other than
0/1 → `raise GitCommandError(["git", "diff", "--cached", "--quiet"], rc, err)`.

## ALGORITHM
```
with open_repo_for_query(project_dir) as repo:
    rc, _, err = run_git_raw(repo, "diff", "--cached", "--quiet")
    if rc == 0: return False
    if rc == 1: return True
    raise GitCommandError([...], rc, err)
```

## DATA
`bool`.

## Tests
- Clean repo → `False`; staged change → `True`; unstaged-only change → `False`.
- Unborn HEAD: nothing staged → `False`; staged new file → `True`.
- Non-repo → `ValueError`. Mocked `run_git_raw` → `(128, b"", "fatal")` → `GitCommandError`.
