# Step 2 — Fail-fast rate-limit cap

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_2.md`), and issue #329
> for context. Implement **only** this step with TDD: write the tests below first, then the
> implementation. Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy; all must pass.
> Run `run_format_code`, then make exactly one commit.

## Precondition

The installed PyGithub must accept `GithubRetry(max_rate_limit_wait=...)` (≥ 2.10.0). Check with
`get_library_source("github.GithubRetry.GithubRetry.__init__")`. If the parameter is missing,
write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/_client.py`
- `pyproject.toml`
- `tests/github_operations/test_client.py`

## WHAT

```python
GITHUB_MAX_RATE_LIMIT_WAIT = 60  # next to GITHUB_REQUEST_TIMEOUT / GITHUB_RETRY_TOTAL

retry=_LoggingGithubRetry(
    total=GITHUB_RETRY_TOTAL,
    max_rate_limit_wait=GITHUB_MAX_RATE_LIMIT_WAIT,
)
```

`pyproject.toml`: `"PyGithub>=2.7.0"` → `"PyGithub>=2.10.0"`.

## HOW

- `_LoggingGithubRetry` inherits `GithubRetry.__init__`; no change to the subclass. urllib3's
  `Retry.new()` carries the cap over to incremented instances via `**kwargs`. Verify this in
  the test below rather than assuming it.
- Update the `build_github_client` docstring: rate-limit waits are capped at 60s; a longer
  primary-limit wait raises `RateLimitExceededExceedsMaxWait` immediately. The cap must stay ≥
  `secondary_rate_wait` (60s) so a secondary limit still waits.

## DATA

- No return-value change; `build_github_client` still returns `Github`.

## Tests (write first)

In `test_client.py`:

- `test_build_github_client_applies_timeout_retry_and_base_url`: add
  `assert call_kwargs["retry"].max_rate_limit_wait == 60`.
- `test_factory_constants_are_load_bearing`: add `assert GITHUB_MAX_RATE_LIMIT_WAIT == 60`.
- New: a primary rate limit with reset 600s away raises immediately. Reuse the 403 stub
  pattern from `_run`, but build the retry as
  `build_github_client(...)`'s retry (patch `Github`, read `call_kwargs["retry"]`) and call
  `.increment("GET", "/user", response=stub)` inside
  `pytest.raises(RateLimitExceededExceedsMaxWait)`.
- New: a secondary rate limit (message `"You have exceeded a secondary rate limit"`, no
  `X-RateLimit-Remaining: 0`) does not raise; `increment` returns a retry whose
  `get_backoff_time()` is 60.
