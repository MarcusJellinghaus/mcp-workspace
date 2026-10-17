# Step 2 — `get_remote_branch_commit_sha` helper

Read `pr_info/steps/summary.md` first for overall context. This step implements
design change (2) from that summary. Independent of step 1.

## Precondition

If `src/mcp_workspace/git_operations/branch_queries.py` does not contain a
`remote_branch_exists` function, or `tests/git_operations/test_branch_queries.py`
does not use a `git_repo_with_remote` fixture, write one line to
`pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/git_operations/branch_queries.py` (modify — add one function)
- `tests/git_operations/test_branch_queries.py` (modify — add tests)

## WHAT

```python
def get_remote_branch_commit_sha(project_dir: Path, branch_name: str) -> Optional[str]:
    """Get the commit sha that origin/<branch_name> currently points to."""
```
Place it directly after `remote_branch_exists` in the same file — it mirrors
that function's shape exactly (validation, `safe_repo_context`, origin-remote
check, ref lookup) but returns a sha instead of a bool.

## HOW

- No new imports — `safe_repo_context`, `logger`, `is_git_repository`,
  `InvalidGitRepositoryError`, `GitCommandError` are already imported in this
  file and reused as-is.
- Follows the exact same guard order as `remote_branch_exists`: not-a-repo →
  `None`; empty/whitespace branch name → `None`; no `origin` remote → `None`;
  `origin/<branch_name>` ref not found → `None`.

## ALGORITHM

```
if not is_git_repository(project_dir) or not branch_name.strip(): return None
with safe_repo_context(project_dir) as repo:
    if "origin" not in [r.name for r in repo.remotes]: return None
    target = f"origin/{branch_name}"
    for ref in repo.remotes.origin.refs:
        if ref.name == target:
            return ref.commit.hexsha
    return None
# except (InvalidGitRepositoryError, GitCommandError): return None
# except Exception: log warning, return None
```

## DATA

Returns `Optional[str]` — the full commit sha, or `None` when the repo, the
`origin` remote, or the specific branch ref cannot be resolved.

## Tests to write first (TDD)

In `tests/git_operations/test_branch_queries.py`, add
`get_remote_branch_commit_sha` to the existing import block, then add a test
class (e.g. `TestGetRemoteBranchCommitSha`, marked `@pytest.mark.git_integration`
like the neighboring `TestBranchExistence` class):

1. `test_returns_sha_for_existing_remote_branch` — using fixture
   `git_repo_with_remote: tuple[Repo, Path, Path]`: push the current branch
   (`repo.git.push("-u", "origin", current_branch)` as the existing
   `test_remote_branch_exists_returns_true` does), then assert
   `get_remote_branch_commit_sha(project_dir, current_branch) == repo.active_branch.commit.hexsha`.
2. `test_returns_none_for_nonexistent_branch` — `git_repo_with_remote` fixture,
   no push; assert `get_remote_branch_commit_sha(project_dir, "nonexistent-branch") is None`.
3. `test_returns_none_no_origin` — `git_repo_with_commit` fixture; assert
   `get_remote_branch_commit_sha(project_dir, "master") is None`.
4. `test_returns_none_not_a_repo` — plain `tmp_path`; assert
   `get_remote_branch_commit_sha(tmp_path, "master") is None`.
5. `test_returns_none_empty_branch_name` — `git_repo_with_remote` fixture;
   assert `get_remote_branch_commit_sha(project_dir, "") is None`.

Confirm all fail (ImportError / AttributeError) before implementing, then
implement and confirm all pass.

## Commit

One commit: tests + implementation + green checks.
Message: `feat(git_operations): add get_remote_branch_commit_sha helper`
