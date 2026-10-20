# Step 2 — Use `_LoggingGithubRetry` in `build_github_client`; fix docstrings

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md`.
> Step 1 (`_LoggingGithubRetry`) is already committed. TDD: extend the factory
> test first, then change the factory. Run pylint, pytest (`-n auto`), mypy;
> all must pass. Run format_code, then make exactly one commit.

## Precondition

If `_LoggingGithubRetry` does not exist in
`src/mcp_workspace/github_operations/_client.py`, write one line to
`pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/_client.py`
- `tests/github_operations/test_client.py`

## WHAT

`build_github_client(token: str, base_url: str) -> Github` — signature unchanged.

## HOW

- Replace `retry=GithubRetry(total=GITHUB_RETRY_TOTAL)` with
  `retry=_LoggingGithubRetry(total=GITHUB_RETRY_TOTAL)`. Timeout unchanged.
- Rewrite the `build_github_client` docstring paragraph to say:
  - timeout=10 with total=2 gives ~30s worst case **on an unreachable host**
    (1 initial + 2 retries);
  - total=2 also caps 403 secondary-rate-limit retries to 2 attempts —
    deliberate, do NOT raise back;
  - rate-limit waits are not capped by the timeout (a primary wait lasts until
    the quota resets, ≤ 1h) and are logged by `_LoggingGithubRetry`.
- Test docstring of `test_factory_constants_are_load_bearing`: say the 30s math
  (10 × (1 + 2 retries)) applies to an unreachable host only; rate-limit waits
  are longer and are logged.

## ALGORITHM

None (one-line wiring change).

## DATA

Returned `Github` instance's `retry` kwarg is a `_LoggingGithubRetry` with
`total == 2`.

## Tests

In `test_build_github_client_applies_timeout_retry_and_base_url` add:

```python
assert type(call_kwargs["retry"]) is _LoggingGithubRetry
```

Keep the existing `total == 2`, timeout and base_url assertions.

## Commit

`feat(github_operations): build clients with _LoggingGithubRetry (#330)`
