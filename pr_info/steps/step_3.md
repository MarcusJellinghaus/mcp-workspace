# Step 3 — `remote_head_sha`

## LLM prompt

> Read `pr_info/steps/summary.md` (design points 4, 5) and this file. Implement step 3 only:
> tests first, then the library change. Run format, pylint, pytest (`-n auto`), mypy,
> lint-imports and ruff; all must pass. Make exactly one commit.

## WHERE

- `src/mcp_workspace/git_operations/core.py`: new `RemoteHeadResult` TypedDict (next to `BranchProbe`).
- `src/mcp_workspace/git_operations/remotes.py`: new `remote_head_sha`.
- New tests: `tests/git_operations/test_remote_head_sha.py`

`_ls_remote_heads`, `probe_origin_branch`, `list_remote_branches` stay unchanged.

## WHAT

```python
class RemoteHeadResult(GitResult):
    """Result of asking origin for one branch's tip.

    ``sha`` is the full SHA, or None when origin has no such branch or could not answer;
    ``success`` tells the two apart.
    """
    sha: str | None

def remote_head_sha(project_dir: Path, branch: str) -> RemoteHeadResult: ...
```

## HOW

- Uses `run_git_timed(project_dir, "ls-remote", "--heads", "origin", f"refs/heads/{branch}")`
  from `._subprocess_git` (timeout + non-interactive env + scrubbing).
- Parses the SHA itself (`parse_ls_remote_heads` returns names only).
- Not exported from `__init__.py`.

## ALGORITHM

```
if not branch.strip() or is_option_like(branch): -> error "Invalid branch name", sha None
out = run_git_timed(...); if not out["success"] -> error result (error, returncode, stderr), sha None
for line in out["stdout"].splitlines():
    sha, _, ref = line.partition("\t")
    if ref == f"refs/heads/{branch}": return success, sha
return success, sha None
```

## DATA

`RemoteHeadResult`: `success`, `error`, `returncode`, `stderr`, `sha`.

## Tests (write first)

Unit (patch `mcp_workspace.git_operations.remotes.run_git_timed`):
- stdout `"<sha>\trefs/heads/x\n"` → `sha == <sha>`.
- stdout with only `refs/heads/team/x` for branch `x` → `sha is None`, `success=True`.
- empty stdout → `sha is None`, `success=True`.
- failure / timeout → `success=False`, `sha is None`, error passed through.
- `"-x"` → validation error, `run_git_timed` not called.

Integration (`git_integration`, bare origin): pushed branch → SHA equals the local tip;
unknown branch → `sha is None`.

## Commit

`feat(git_operations): add remote_head_sha via timeout-bounded ls-remote`
