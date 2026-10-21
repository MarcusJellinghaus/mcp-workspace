# Step 3 — `PRChecksMixin.get_non_green_checks`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md` exactly.
> TDD: write `tests/github_operations/test_pr_checks_mixin.py` first, see it fail, then add the
> mixin. Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy and lint-imports; all must pass.
> Run `run_format_code`, then make one commit.

## WHERE

- New: `src/mcp_workspace/github_operations/pr_checks_mixin.py`
- Modified: `src/mcp_workspace/github_operations/pr_manager.py`, which adds `PRChecksMixin` to the bases
- New: `tests/github_operations/test_pr_checks_mixin.py`

## WHAT

```python
_PASSING_CHECK_CONCLUSIONS: frozenset[str] = frozenset({"success", "neutral", "skipped"})
PERMISSION_ERROR_TEXT = "token lacks permission (Checks: read / Commit statuses: read)"

def _classify_lookup_error(e: BaseException) -> str: ...

class PRChecksMixin:
    @log_function_call
    def get_non_green_checks(
        self: "PullRequestManager", pr_number: int, head_sha: Optional[str] = None
    ) -> tuple[tuple[str, ...], Optional[str]]: ...
```

## HOW

- Follow the layout of `pr_merge_mixin.py`: `from __future__ import annotations`, `TYPE_CHECKING`
  import of `PullRequestManager`, and `__all__ = ["PRChecksMixin"]`.
- Imports: `GithubException` from `github.GithubException`; `format_rate_limit_error` from
  `._diagnostics`; `_format_error_message` from `.base_manager`.
- **Do NOT** decorate with `_handle_github_errors`. That decorator re-raises rate-limit and 401/403
  errors, and this method must never raise.
- `pr_manager.py`: `class PullRequestManager(PRReviewMixin, PRMergeMixin, PRFeedbackMixin, PRChecksMixin, BaseGitHubManager)`.
- Docstring: state the non-green rules, and note that only the first page of commit statuses is read.

## ALGORITHM

```
try:
    repo = self._get_repository()
    if repo is None: return ((), self._last_repository_error or "repository not accessible")
    sha = head_sha or repo.get_pull(pr_number).head.sha
    commit = repo.get_commit(sha)
    names = [f"{s.context} ({s.state})" for s in commit.get_combined_status().statuses if s.state != "success"]
    for run in commit.get_check_runs():          # PaginatedList: iterates all pages
        if run.status != "completed": names.append(f"{run.name} ({run.status})")
        elif run.conclusion not in _PASSING_CHECK_CONCLUSIONS: names.append(f"{run.name} ({run.conclusion})")
    return (tuple(names), None)
except Exception as e:  # pylint: disable=broad-exception-caught
    logger.debug("Check lookup failed", exc_info=True); return ((), _classify_lookup_error(e))
```

`_classify_lookup_error(e)`:

```
msg = format_rate_limit_error(e)
if msg is not None: return msg
if isinstance(e, GithubException) and e.status in (401, 403): return PERMISSION_ERROR_TEXT
return _format_error_message(e)
```

## DATA

Returns `(names, error)`:

- success → `(("codecov/patch (pending)", "lint (failure)"), None)`, or `((), None)` when everything is green
- failure → `((), "<reason>")`, where the reason is the rate-limit text (including the reset time),
  `PERMISSION_ERROR_TEXT`, or `"GitHub API error 500: ..."` / `"network error: ConnectionError"`

Each entry is formatted as `name (state)`. Statuses come first, then check runs, in API order.

## Tests (write first)

Use a `manager` fixture like the one in `test_pr_merge_mixin.py` (git repo with remote, patched
`_client.Github` and `get_github_token`; mark the class `git_integration`). Mock
`mock_repo.get_commit.return_value` with `get_combined_status().statuses` and `get_check_runs()`
returning plain lists of `MagicMock`s.

1. Check runs: `completed`+`success`/`neutral`/`skipped` are excluded; `completed`+`failure`,
   `cancelled`, `timed_out`, `action_required` are included; `in_progress` and `queued` are
   included with their status.
2. Statuses: `success` is excluded; `pending`, `failure`, `error` are included.
3. All green → `((), None)`.
4. `head_sha` given → `repo.get_pull` is not called and `get_commit` is called with that SHA;
   `head_sha=None` → SHA is resolved from `repo.get_pull(pr_number).head.sha`.
5. `GithubException(403, {"message": "Resource not accessible"}, headers={})` from `get_check_runs`
   → error is `PERMISSION_ERROR_TEXT`.
6. Rate limit: `GithubException(403, ..., headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "<epoch>"})`
   → error starts with `"GitHub rate limit exhausted"` and contains `"resets at"`.
7. `GithubException(500, {"message": "boom"})` → `"GitHub API error 500: boom"`; a
   `ConnectionError` raised while iterating → `"network error: ConnectionError"`.
8. Not one of these cases raises.
