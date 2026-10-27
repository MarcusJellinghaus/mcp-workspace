# Step 1: `GitHubRateLimitError` + issue cache raises on rate limit

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md` exactly.
> TDD: write the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy;
> all must pass. One commit.

## Precondition (check first)

#360 must be merged. Check both:
- `src/mcp_workspace/github_operations/issues/_cache_io.py` exists and its
  `_save_cache_file` uses `tempfile.mkstemp`;
- `get_pr_feedback` in `src/mcp_workspace/github_operations/pr_feedback_mixin.py`
  has an `include_alerts` parameter.

If either does not hold: write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- Create `src/mcp_workspace/github_operations/caching/__init__.py` — module docstring only, **no imports**.
- Create `src/mcp_workspace/github_operations/caching/errors.py`
- Modify `src/mcp_workspace/github_operations/__init__.py` — import and add `"GitHubRateLimitError"` to `__all__`.
- Modify `src/mcp_workspace/github_operations/issues/cache.py`
- Tests: `tests/github_operations/caching/__init__.py` (empty),
  `tests/github_operations/caching/test_errors.py`,
  `tests/github_operations/issues/test_cache_rate_limit.py`

## WHAT

```python
# caching/errors.py
class GitHubRateLimitError(Exception):
    """GitHub rate limit hit; the caller should stop this run. Nothing was cached."""
    def __init__(self, message: str, reset_at: datetime | None = None) -> None: ...
    message: str
    reset_at: datetime | None

def to_rate_limit_error(exc: BaseException) -> GitHubRateLimitError | None:
    """Return a GitHubRateLimitError for a rate-limit exc, else None."""

@contextmanager
def rate_limit_guard() -> Iterator[None]:
    """Re-raise any rate-limit exception as GitHubRateLimitError (``from exc``)."""
```

## HOW

- Rule: `format_rate_limit_error(exc) is not None` (from `.._diagnostics`). This includes
  `RetryError` with unknown status — deliberate.
- `reset_at`: for a `GithubException`, read `X-RateLimit-Reset` case-insensitively from
  `exc.headers`; epoch digits → `datetime.fromtimestamp(..., tz=timezone.utc)`; else `None`.
- `rate_limit_guard` must not wrap an already-converted `GitHubRateLimitError`
  (it is not a GithubException/RetryError, so `to_rate_limit_error` returns None — fine).
- `issues/cache.py`:
  - `get_all_cached_issues`: in the `except Exception` around step 4–6, first
    `if (rl := to_rate_limit_error(e)) is not None: raise rl from e`; else keep stale return.
  - `_fetch_additional_issues`: same check at the top of its `except` → raise.
    Since it runs before any save, no file is written.
  - Also make sure any additional-issues save on the duplicate-protection path (#360 §2)
    is not reached when the raise happens (it is after the fetch — verify by test).

## ALGORITHM

```
def to_rate_limit_error(exc):
    msg = format_rate_limit_error(exc)
    if msg is None: return None
    return GitHubRateLimitError(msg, _reset_at(exc))
rate_limit_guard: try: yield / except Exception as e: if (rl := to_rate_limit_error(e)): raise rl from e; raise
```

## DATA

`GitHubRateLimitError.args == (message,)`; `str(err) == message`.

## Tests

`test_errors.py`:
- `RateLimitExceededException`, 429, `X-RateLimit-Remaining: 0` → converted; `reset_at` set from header, `None` without.
- `make_retry_error(403)` and unknown-status `RetryError` → converted; `make_retry_error(500)` → None.
- Plain 404 `GithubException`, `ValueError` → None; `rate_limit_guard` re-raises them unchanged.
- `from mcp_workspace.github_operations import GitHubRateLimitError` works.

`test_cache_rate_limit.py` (follow the fixtures/patching style of `test_cache_refresh.py`):
- Incremental list raises a rate-limit `GithubException` → `GitHubRateLimitError`, `_save_cache_file` not called.
- `_fetch_additional_issues` `get_issue` raises rate limit → `GitHubRateLimitError`, nothing saved (both normal and duplicate-protection paths).
- Non-rate-limit error (500) → stale data returned as today.
