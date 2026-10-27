# Step 4: Retry lines in `_LoggingGithubRetry.increment` + end-to-end line counts

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md` only.
> TDD: write the tests first, then the implementation. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`) and mypy until all pass. Format with `run_format_code`,
> then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/github_operations/_client.py` — new `increment` override
- `tests/github_operations/test_client_traffic_log.py` — new tests

## WHAT

```python
class _LoggingGithubRetry(GithubRetry):
    def increment(  # type: ignore[override]
        self,
        method: str | None = None,
        url: str | None = None,
        response: BaseHTTPResponse | None = None,
        error: Exception | None = None,
        _pool: ConnectionPool | None = None,
        _stacktrace: TracebackType | None = None,
    ) -> Retry:
        """Write a ``retry`` traffic line when another attempt follows."""
```

Use `TYPE_CHECKING` imports for `ConnectionPool`, `TracebackType`, `Retry`, matching the
existing `BaseHTTPResponse` import. Update the class docstring.

## HOW

- `super().increment(...)` is called first. If it raises (wait cap, retries exhausted,
  non-rate-limit 403), nothing is written; the exception leaves `__requestRaw` and the step 3
  wrapper writes the `ERR` line.
- `increment` sees urllib3's case-insensitive headers; `log_request` handles both.
- The existing `sleep` override stays unchanged.

## ALGORITHM

```
new_retry = super().increment(method, url, response, error, _pool, _stacktrace)
if response is not None: status, headers = f"retry {response.status}", response.headers
else: status, headers = f"retry {type(error).__name__}", None
log_request(method or "-", url or "-", status, headers, None)
return new_retry
```

## DATA

- Retry line: `... | GET /x | retry 500 | core 4210 | - | <chain>`;
  without a response: `... | GET /x | retry ReadTimeoutError | - - | - | <chain>`.

## Tests

Enable the log as in step 3.

Direct `increment` tests (as in `test_client.py`, `urllib3.HTTPResponse` stubs):
- `error=ReadTimeoutError(None, "/x", "timed out")`, `response=None`, method `GET` → one
  `retry ReadTimeoutError` line with `- -`
- 403 primary rate limit with reset 600 s away → raises `RateLimitExceededExceedsMaxWait`, no line
- 403 with message `"Resource not accessible by integration"` → raises, no line
- log off (fixture default) → no file

End-to-end through urllib3 (no fakes in PyGithub): a local `http.server.ThreadingHTTPServer` on
`127.0.0.1:0` in a daemon thread serves a scripted sequence of responses; build
`build_github_client("tok", f"http://127.0.0.1:{port}")` and call
`client.requester.requestJsonAndCheck("GET", "/x")`. Patch `urllib3.util.retry.time.sleep`
to skip backoff waits.
- 500, then 200 → exactly 1 `retry 500` line + 1 `200` line
- 403 `{"message": "API rate limit exceeded for user ID 1."}` with `X-RateLimit-Remaining: 0`,
  `X-RateLimit-Reset` 600 s away → exactly 1 line, `ERR RateLimitExceededExceedsMaxWait 403`,
  no `retry` line
- 301 `Location: http://127.0.0.1:<port>/y`, then the same rate-limit 403 → exactly 1 `ERR` line
- 403 `{"message": "Resource not accessible by integration"}` → exactly 1 line ending `ERR ... 403`
  (assert the `ERR ` prefix and the ` 403` suffix of the status field, not the exact class name)

If urllib3 never calls `increment` for the scripted 500 (no `retry` line appears and the
request fails or succeeds without a retry), write one line to `pr_info/.blocked.txt` and stop.
