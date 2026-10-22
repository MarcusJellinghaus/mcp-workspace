# Step 1 — `get_head_commit_info` git helper

Read `pr_info/steps/summary.md` first. One commit: tests + implementation, all checks passing.

## LLM prompt

> Implement Step 1 of `pr_info/steps/summary.md` as described in `pr_info/steps/step_1.md`.
> Write the tests first, then the helper. Run pylint, mypy, pytest (`-n auto`), tach and
> lint-imports; format code; commit once.

## WHERE

- `src/mcp_workspace/git_operations/commits.py` — new function directly after `get_latest_commit_sha`
- `src/mcp_workspace/git_operations/__init__.py` — import + `__all__` entry (alphabetical)
- `tests/git_operations/test_commits.py` — new test class

## WHAT

```python
def get_head_commit_info(project_dir: Path) -> Optional[tuple[str, datetime]]:
    """Get HEAD's short SHA and committer date in UTC.

    Committer date, not author date: a rebase rewrites the committer date.

    Returns:
        (short SHA, tz-aware UTC committer datetime), or None if HEAD
        cannot be read.
    """
```

## HOW

- Imports in `commits.py`: `from datetime import datetime, timezone`. `GIT_SHORT_HASH_LENGTH` and
  `safe_repo_context` are already imported from `.core`.
- Same `try/except` shape as `get_latest_commit_sha`.

## ALGORITHM

```
try:
    with safe_repo_context(project_dir) as repo:
        commit = repo.head.commit
        return commit.hexsha[:GIT_SHORT_HASH_LENGTH], commit.committed_datetime.astimezone(timezone.utc)
except (InvalidGitRepositoryError, GitCommandError, ValueError, OSError):
    return None
```

## DATA

`tuple[str, datetime]` — 7-char SHA, tz-aware datetime with `tzinfo == timezone.utc`; or `None`.

## Tests (`tests/git_operations/test_commits.py`)

Add `get_head_commit_info` to the existing import from `mcp_workspace.git_operations.commits`.

```python
@pytest.mark.git_integration
class TestGetHeadCommitInfo:
    def test_returns_short_sha_and_utc_committer_date(self, git_repo: tuple[Repo, Path]) -> None:
        # Create + stage a file, then commit with differing dates and a non-UTC committer offset:
        # repo.index.commit("msg", author_date="2026-01-01T08:00:00+00:00",
        #                   commit_date="2026-01-02T12:00:00+02:00")
        # Assert: sha == repo.head.commit.hexsha[:7]
        #         committed == datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
        #         committed.tzinfo == timezone.utc

    def test_returns_none_outside_git_repo(self, tmp_path: Path) -> None:
        # assert get_head_commit_info(tmp_path) is None
```

The first test covers SHA length, committer-not-author, and UTC conversion in one go.
