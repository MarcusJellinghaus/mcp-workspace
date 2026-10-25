# Step 8 — `list_remote_branches`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 8 only, tests first, reusing
`_ls_remote_heads` and `parse_ls_remote_heads` from step 7. Run the checks from the summary,
format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/core.py` (add `RemoteBranchesResult`)
- `src/mcp_workspace/git_operations/remotes.py` (add function)
- `src/mcp_workspace/git_operations/__init__.py` (export function + type; count +2)
- `tests/git_operations/test_remote_queries.py`
- `vulture_whitelist.py`

## WHAT
```python
class RemoteBranchesResult(GitResult):
    branches: list[str]

def list_remote_branches(project_dir: Path) -> RemoteBranchesResult:
    """All heads on origin (network), no truncation."""
```

## HOW
No `git()` dispatcher (it truncates at 100 lines and returns "No output." when empty).

## ALGORITHM
```
open repo (non-repo -> success=False, branches=[], returncode=None)
rc, out, err = _ls_remote_heads(repo)
rc != 0 -> success=False, branches=[], error=f"git ls-remote failed (exit {rc})", rc, err
return success=True, branches=parse_ls_remote_heads(out), rc, err
```

## DATA
`RemoteBranchesResult`; failure is `success=False` (never a successful empty list).

## Tests
- 120 branches pushed to the bare remote (create with `update-ref` + one `push --all`) →
  all 120 returned.
- Remote with only `main` → `["main"]`.
- Empty bare remote (nothing pushed) → `success=True`, `branches=[]`.
- Unreachable remote → `success=False`.

## vulture
`_.branches`.
