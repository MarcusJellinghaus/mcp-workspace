# Summary — #330: Log an INFO message when a GithubRetry sleep exceeds 15s

## Goal

`GithubRetry` can block a single API call for minutes (primary rate limit: until
`X-RateLimit-Reset + 1s`; secondary: 60s; `Retry-After`: header value). Its only
trace is on the `github.GithubRetry` logger, which mcp-coder filters to WARNING,
so callers look hung. Make every wait > 15s visible on **mcp-workspace's own
logger**. Behaviour (what is slept, how often, what is raised) is unchanged.

## Architectural / design changes

- **New private retry subclass** `_LoggingGithubRetry(GithubRetry)` in
  `github_operations/_client.py`. It overrides only `sleep(response=None)`:
  computes the wait exactly as urllib3 will, logs one INFO record if the wait is
  > 15s, then delegates to `super().sleep(response)`.
- **Hook point is `sleep()`**, not `increment()`. Verified against installed
  PyGithub/urllib3:
  - urllib3 calls `retries.increment(...)` then `retries.sleep(response)` on the
    returned instance.
  - `GithubRetry.increment` patches `get_backoff_time` on that returned instance
    with the real rate-limit wait → `self.get_backoff_time()` inside `sleep()` is
    already correct.
  - `Retry.new()` uses `type(self)(**params)`; `GithubRetry.new` forwards its
    kwargs → the subclass survives every `increment`.
- **Reason from headers only** (body is already drained when `sleep()` runs):
  `Retry-After` present → Retry-After; `X-RateLimit-Remaining == "0"` → primary;
  else → secondary.
- **Factory change:** `build_github_client` passes
  `retry=_LoggingGithubRetry(total=GITHUB_RETRY_TOTAL)`. Timeout and `total`
  unchanged. Retry policy still lives in exactly one place.
- **Docstring correction:** the "~30s worst case" applies only to an unreachable
  host; rate-limit waits are not capped by the timeout (primary ≤ 1h) and are
  logged by `_LoggingGithubRetry`.
- No new dependencies. `urllib3.BaseHTTPResponse` is imported only under
  `TYPE_CHECKING` (import-linter and tach both ignore type-checking imports).

## Log messages (seconds rounded; suffix ` (METHOD url)` from `self.history[-1]` if history non-empty)

- Primary: `GitHub REST rate limit exhausted for this token, waiting 597s for the quota to reset (resets 05:22:03 UTC) (GET /user)`
  — `(resets …)` omitted if `X-RateLimit-Reset` is missing or not all digits.
- Secondary: `GitHub secondary rate limit hit, waiting 60s before retrying (GET /user)`
- Retry-After: `GitHub requested a retry after 120s (Retry-After header), waiting (GET /user)`

## Files

| File | Change |
|------|--------|
| `src/mcp_workspace/github_operations/_client.py` | modify — `__future__` import, logger, `_LoggingGithubRetry`, factory wiring, docstring |
| `tests/github_operations/test_client.py` | modify — retry-chain tests, factory type assertion, docstring |

No files or folders are created besides these plan files.

## Steps

1. `step_1.md` — `_LoggingGithubRetry` class + tests running the real `increment` → `sleep` chain.
2. `step_2.md` — wire it into `build_github_client`, fix both docstrings, assert retry type.

## Out of scope

- Redirect `Retry-After` path (`sleep_for_retry` called directly by urllib3).
- Capping waits via `max_rate_limit_wait` (behaviour change).
- Waits that already log (CI/PR polling, 1s/2s/4s manual retries).
