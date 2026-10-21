# Step 4 — Rate-limit reporting and re-raise in `base_manager`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_4.md`), and issue #329
> (section "Rate-limit error message", users 1–3) for context. Implement **only** this step
> with TDD: write the tests below first, then the implementation. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`) and mypy; all must pass. Run `run_format_code`, then make
> exactly one commit.

## WHERE

- `src/mcp_workspace/github_operations/base_manager.py`
- `tests/github_operations/test_base_manager.py`

## WHAT

No new functions. Import `format_rate_limit_error` from `._diagnostics` and add one inline
check to each of these `except` branches, keeping the rest of each branch unchanged:

| Function | Branch | On rate limit |
|---|---|---|
| `_handle_github_errors.wrapper` | `except GithubException` (before the 401/403 check) | `logger.error(f"{msg} in {func.__name__}")`; `raise` |
| `_handle_github_errors.wrapper` | `except Exception` | same |
| `BaseGitHubManager._get_repository` | `except GithubException` (after the existing DEBUG log) | `logger.error("%s (repository %s)", msg, repo_url)`; `raise` |
| `BaseGitHubManager._get_repository` | `except Exception` (before `maybe_log_network_diagnostics`) | same, with `full_name`; `raise` |
| `get_authenticated_username` | `except GithubException` (after the existing DEBUG log) | `logger.error(msg)`; `raise ValueError(msg) from e` |
| `get_authenticated_username` | `except Exception` (before `maybe_log_network_diagnostics`) | same |

## HOW

Pattern used at every site:

```python
msg = format_rate_limit_error(e)
if msg is not None:
    logger.error(...)
    raise  # or: raise ValueError(msg) from e
```

- Update the `_handle_github_errors` docstring: add "Rate-limit errors (403 rate limit, 429,
  `RetryError`): logged and re-raised" as the first bullet.
- Update the `_get_repository` docstring "Returns/Raises": rate-limit errors propagate.
- `get_authenticated_username` keeps raising `ValueError` (mcp-coder catches it).

## DATA

- `_get_repository` → `Optional[Repository]` unchanged; additionally raises
  `GithubException` / `RetryError` for rate limits.

## Tests (write first)

Rate-limit fixtures: `GithubException(403, {"message": "API rate limit exceeded"},
{"x-ratelimit-remaining": "0", "x-ratelimit-resource": "core", "x-ratelimit-reset": str(int(time.time()) + 600)})`,
`GithubException(429, {"message": "Too Many Requests"}, {})`,
`requests.exceptions.RetryError("retries exhausted")`.

- `TestHandleGitHubErrorsDecorator`: parametrized over 429 and `RetryError` → re-raised (not
  the default); 403 rate limit → re-raised and the ERROR log contains `` `core` ``. Existing
  tests for 500 / generic errors returning the default stay green.
- `_get_repository` (new class `TestGetRepositoryRateLimit`, set up like
  `TestGetRepositoryDebugLogging`): parametrized over the three rate-limit errors as
  `get_repo` side effect → `pytest.raises(type(err))`; parametrized over
  `GithubException(404)`, `GithubException(500)`, `ConnectionError()` → returns `None`.
- `get_authenticated_username`: `get_user` raising the 403 rate limit → `ValueError` whose text
  contains `` `core` rate limit `` and not "Failed to authenticate"; `RetryError` →
  `ValueError` containing "retries exhausted"; `GithubException(401)` → still
  "Failed to authenticate with GitHub".
