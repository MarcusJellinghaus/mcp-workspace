# Step 8 — `PullRequestManager.find_merged_pr_by_head_sha`

## LLM prompt

> Read `pr_info/steps/summary.md` (design point 8) and this file. Implement step 8 only:
> tests first, then the new method. Run format, pylint, pytest (`-n auto`), mypy,
> lint-imports and ruff; all must pass. Make exactly one commit.

## WHERE

- `src/mcp_workspace/github_operations/pr_manager.py` (next to `find_pull_request_by_head`,
  which stays unchanged).
- New tests: `tests/github_operations/test_pr_manager_merged_by_sha.py`

## WHAT

```python
@log_function_call
@_handle_github_errors(None)
def find_merged_pr_by_head_sha(self, sha: str) -> int | None:
    """Return the number of a merged PR whose head SHA is ``sha``, else None."""
```

## HOW

- One API call: `repo.get_commit(sha).get_pulls()`; read `merged_at` and `head.sha` from the
  list payload (no `_pr_to_data`, no lazy per-PR GET). Works after GitHub deleted the branch.
- `_handle_github_errors(None)`: a 404/422 for an unknown commit returns None; auth (401/403)
  and rate-limit errors are re-raised — the caller (step 10) treats any exception as
  "check skipped".
- Reject a `sha` that is not 40 hex chars with `None` before any call.

## ALGORITHM

```
if not re.fullmatch(r"[0-9a-f]{40}", sha): return None
repo = self._get_repository(); if repo is None: return None
for pr in repo.get_commit(sha).get_pulls():
    if pr.merged_at is not None and pr.head.sha == sha: return pr.number
return None
```

## DATA

`int | None` — the PR number.

## Tests (write first)

Unit (mock the repository as the existing `tests/github_operations/test_pr_manager.py` does):
- one merged PR with matching head → its number.
- PR with matching head but `merged_at=None` → None.
- merged PR whose `head.sha` differs → None.
- `GithubException(422)` from `get_commit` → None.
- `GithubException(401)` → raised.
- short / non-hex sha → None, no API call.

## Commit

`feat(github_operations): add find_merged_pr_by_head_sha`
