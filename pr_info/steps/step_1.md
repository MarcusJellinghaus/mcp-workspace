# Step 1 — `alert_skip_status` classifier

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md` exactly.
> TDD: write the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy;
> all must pass. Format, then make exactly one commit.

## WHERE

- `src/mcp_workspace/github_operations/_pr_feedback_sources.py`
- `src/mcp_workspace/github_operations/pr_feedback_mixin.py`
- `tests/github_operations/test_pr_feedback_mixin.py` (new test class next to the existing
  `fetch_code_scanning_alerts` tests; add `alert_skip_status` to the existing
  `_pr_feedback_sources` import)

## WHAT

```python
def alert_skip_status(exc: BaseException) -> int | None:
    """Return 403/404 when a code-scanning alerts error means "not checked", else None.

    A skip is status 403/404 that is not a rate limit (token lacks
    security_events:read, code scanning disabled, or no analysis exists).
    Pure: callers decide whether to route or raise.
    """
```

Place it directly after `fetch_code_scanning_alerts`. Import `format_rate_limit_error`
from `._diagnostics` in `_pr_feedback_sources.py`.

## HOW

- `_collect_pr_feedback` alerts `except` block: replace the inline status /
  `format_rate_limit_error` condition with `alert_skip_status(e) is not None`, called
  through the module (`_pr_feedback_sources.alert_skip_status(e)`), as the fetcher is.
  Keep the debug / warning log lines and the `skipped` / `unavailable` routing unchanged.
- Remove the now-unused `from ._diagnostics import format_rate_limit_error` from
  `pr_feedback_mixin.py`.
- Update the `_pr_feedback_sources.py` module docstring: the helpers are used by
  `PullRequestManager.get_pr_feedback()` and by the PR cache
  (`caching/pull_requests.py`); still private to the `github_operations` package.

## ALGORITHM

```
status = getattr(exc, "status", None)
if status in (403, 404) and format_rate_limit_error(exc) is None:
    return status
return None
```

## DATA

`int | None` — `403` / `404`, or `None` (rate limit, other status, `RetryError`,
non-GitHub exception).

## Tests (write first)

One parametrized test `test_alert_skip_status` with ids:

| case | expected |
|---|---|
| `GithubException(403, {"message": "forbidden"}, None)` | `403` |
| `GithubException(404, {...}, None)` | `404` |
| `UnknownObjectException(404, {...}, None)` | `404` |
| rate-limited 403 (`x-ratelimit-remaining: 0`, as in `test_code_scanning_error_routing`) | `None` |
| `make_retry_error(403)` | `None` |
| `make_retry_error(500)` | `None` |
| `RetryError()` with unknown status | `None` |
| `GithubException(500, ...)` | `None` |
| `ValueError("x")` | `None` |

Import `make_retry_error` from `.conftest` (`tests/github_operations/conftest.py`) and
`RetryError` from `requests.exceptions`.

The existing `test_code_scanning_error_routing` must still pass unchanged.
