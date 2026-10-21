# Step 1 — `format_rate_limit_error` and extra diagnostic headers

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_1.md`), and issue #329
> for context. Implement **only** this step with TDD: write the tests below first, then the
> implementation. Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy and lint-imports;
> all must pass. Run `run_format_code`, then make exactly one commit.

## WHERE

- `src/mcp_workspace/github_operations/_diagnostics.py`
- `tests/github_operations/test_diagnostics.py`

## WHAT

```python
from requests.exceptions import RetryError
from github.GithubException import GithubException, RateLimitExceededException

DIAGNOSTIC_HEADERS  # + "X-RateLimit-Reset", "X-RateLimit-Used", "X-RateLimit-Resource"

def format_rate_limit_error(exc: BaseException) -> str | None:
    """Describe a GitHub rate-limit failure, or return None for any other error."""
```

## HOW

- Pure function, no logging, no side effects. Callers are added in later steps.
- Header lookup is case-insensitive (Requester-built exceptions lowercase header names;
  GithubRetry-raised ones keep original casing) — lowercase the keys once, like
  `extract_diagnostic_headers`.
- Update the module docstring: it now also recognises rate-limit failures. (The
  "not re-exported" sentence is adjusted in step 3 when the re-export happens — leave it here.)

## ALGORITHM

```
if exc is RetryError: return "GitHub rate limit: retries exhausted"
if exc is not GithubException: return None
h = {k.lower(): v for k, v in (exc.headers or {}).items()}
if not (isinstance(exc, RateLimitExceededException) or exc.status == 429
        or h.get("x-ratelimit-remaining") == "0"): return None
msg = f"GitHub `{resource}` rate limit exhausted" if resource else "GitHub rate limit exhausted"
if reset header is digits: msg += f"; resets at {HH:MM} UTC (in {max(0, ceil(minutes))} min)"
return msg
```

## DATA

- Returns `str` (e.g. ``"GitHub `core` rate limit exhausted; resets at 14:32 UTC (in 9 min)"``)
  or `None`.
- `RateLimitExceededExceedsMaxWait` is a subclass of `RateLimitExceededException` and carries
  the response headers, so it is covered by the `isinstance` check.

## Tests (write first)

In `test_diagnostics.py`:

- Update `test_diagnostic_headers_contains_expected_seven` → expected set of ten (rename the
  test accordingly).
- One parametrized test for `format_rate_limit_error` returning `None`:
  plain `GithubException(403, {"message": "Forbidden"}, {})`, `GithubException(500, ...)`,
  `ValueError("x")`, `ConnectionError()`.
- Rate-limit cases (reset = `int(time.time()) + 600`; no time mocking — assert on the bucket,
  the `HH:MM` derived from the same reset value, and `re.search(r"in \d+ min", msg)`):
  - `GithubException(403, ..., {"x-ratelimit-remaining": "0", "x-ratelimit-resource": "core", "x-ratelimit-reset": ...})` (lowercase keys)
  - `RateLimitExceededExceedsMaxWait(403, ..., {"X-RateLimit-Remaining": "0", "X-RateLimit-Resource": "core", "X-RateLimit-Reset": ...}, wait=600)` (original casing)
  - `GithubException(429, ..., {"x-ratelimit-resource": "search"})` → mentions `search`, no "resets".
  - Rate limit without headers → `"GitHub rate limit exhausted"`.
  - `requests.exceptions.RetryError("x")` → `"GitHub rate limit: retries exhausted"`.
