# Step 7 — `probe_origin_branch` + `origin_has_branch` wrapper

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 7 only, tests first. Keep
`origin_has_branch` in `base_branch.py` under the same name (tests patch
`mcp_workspace.git_operations.base_branch.origin_has_branch`). Run the checks from the
summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/porcelain_parsers.py` (add `parse_ls_remote_heads`)
- `src/mcp_workspace/git_operations/core.py` (add `BranchProbe`)
- `src/mcp_workspace/git_operations/remotes.py` (add `_ls_remote_heads`, `probe_origin_branch`)
- `src/mcp_workspace/git_operations/base_branch.py` (rewrite `origin_has_branch` as wrapper)
- `src/mcp_workspace/git_operations/__init__.py` (export function + `BranchProbe`; count +2)
- `tests/git_operations/test_porcelain_parsers.py`, `tests/git_operations/test_remote_queries.py` (new)
- `vulture_whitelist.py`

## WHAT
```python
# porcelain_parsers.py
def parse_ls_remote_heads(output: bytes) -> list[str]:
    """'<sha>\\trefs/heads/<name>\\n'... -> branch names (UTF-8), order kept."""

# core.py
class BranchProbe(GitResult):
    exists: Optional[bool]   # None = origin couldn't answer

# remotes.py
def _ls_remote_heads(repo: Repo, *refs: str) -> tuple[int, bytes, str]:
    """run_git_raw(repo, "ls_remote", "--heads", "origin", *refs, env=GIT_NONINTERACTIVE_ENV)"""
def probe_origin_branch(project_dir: Path, branch: str) -> BranchProbe: ...

# base_branch.py
def origin_has_branch(project_dir: Path, branch_name: str) -> bool: ...
```

## HOW
- `probe_origin_branch` always queries the full ref `refs/heads/<branch>`; no `--exit-code`.
- Empty/blank branch → error result (`exists=None`, `returncode=None`). Non-repo → same.
- Wrapper: `probe = probe_origin_branch(...)`; if `probe["exists"] is None`: raise
  `GitCommandError(["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch_name}"],
  probe["returncode"], probe["stderr"] or probe["error"] or "")`; else return
  `probe["exists"]`. `base_branch.py` imports `probe_origin_branch` from `.remotes` (no cycle:
  `remotes` does not import `base_branch`). Update the wrapper's docstring.

## ALGORITHM
```
probe_origin_branch:
  rc, out, err = _ls_remote_heads(repo, f"refs/heads/{branch}")
  rc != 0 -> success=False, exists=None, error=f"git ls-remote failed (exit {rc})", rc, err
  return success=True, exists=bool(out.strip()), rc, err
```

## DATA
`BranchProbe`: `success=True` iff `exists` is `True`/`False`.

## Tests
- Parser: two heads; non-ASCII branch; empty output → `[]`.
- Pushed branch → `exists=True`; absent → `exists=False`, `success=True`.
- Fresh clone of the bare remote (no local `origin/<branch>` for a branch pushed after the
  clone) → `exists=True`.
- `team/main` pushed but not `main` → `exists=False` for `main`.
- Unreachable remote (`git remote set-url origin <missing dir>`) → `success=False`,
  `exists is None`, `returncode` nonzero.
- Wrapper raises `GitCommandError` for the unreachable remote; existing tests in
  `test_base_branch_git.py` keep passing unchanged.

## vulture
`_.exists`.
