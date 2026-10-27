# Step 5: Raw download logging in `CIResultsManager`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md` only.
> TDD: write the tests first, then the implementation. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`) and mypy until all pass. Format with `run_format_code`,
> then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/github_operations/ci_results_manager.py` — `_download_and_extract_zip`
- `tests/github_operations/test_ci_results_manager_logs.py` (and
  `tests/github_operations/test_ci_results_manager_artifacts.py` where its mocks need it)

## WHAT

No new functions. `_download_and_extract_zip(self, url: str) -> Dict[str, str]` logs its
`requests.get` call. It serves `get_run_logs` and `get_artifacts`.

## HOW

- Imports: `import time`, `from mcp_workspace.traffic_log import error_status, log_request`.
- Log the original API `url` (no signed blob URL). `log_request` strips scheme and host.
- Rate-limit headers come from the API's response, which is the first redirect hop when
  there was one: `response.history[0]` if `response.history` else `response`.
- The existing outer `try/except` and the `{}` fallback stay unchanged.
- Existing tests use `Mock()` responses; `Mock().history` is a truthy non-subscriptable Mock.
  Set `mock_response.history = []` in those tests.

## ALGORITHM

```
start = time.monotonic()
try: response = requests.get(...)            # unchanged arguments
except Exception as exc:
    log_request("GET", url, error_status(exc), None, ms(start)); raise
first = response.history[0] if response.history else response
log_request("GET", url, str(response.status_code), first.headers, ms(start))
response.raise_for_status()                  # unchanged from here on
```

## DATA

- Line: `... | GET /repos/o/r/actions/runs/123/logs | 200 | core 4100 | 950ms | ci_results_manager.CIResultsManager.get_run_logs > ci_results_manager.CIResultsManager._download_and_extract_zip`

## Tests

Enable with `monkeypatch.setattr("mcp_workspace.config.get_traffic_log_dir", lambda: tmp_path)`.

- success with `history = [redirect]`, where `redirect.headers` carries
  `X-RateLimit-Resource: core` / `X-RateLimit-Remaining: 4100` → one line with
  `GET /repos/test/repo/actions/runs/123/logs | 200 | core 4100`, and the chain contains
  `CIResultsManager._download_and_extract_zip`
- `requests.get` raises `requests.exceptions.ReadTimeout` → one `ERR ReadTimeout` line; method returns `{}`
- 404 (`raise_for_status` raises) → one line with status `404`; method returns `{}`
- log off (fixture default) → no file; existing tests still pass
