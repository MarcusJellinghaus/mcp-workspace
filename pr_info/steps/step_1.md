# Step 1 — Helper refactor: return elapsed `float` + deadline-aware sleep

**Reference:** [summary.md](./summary.md) — see "Implementation Steps".

## LLM Prompt

> Read `pr_info/steps/summary.md` first, then implement this step (`pr_info/steps/step_1.md`) in a single commit using TDD: update tests first, then change `_wait_for_ci` and `_wait_for_pr`. After every edit, run `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_mypy_check`, and `mcp__tools-py__run_pytest_check` (with `extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]`). Do not change `async_poll_branch_status`, the server tool, or `BranchStatusReport`. Commit with message `refactor(branch_status): wait helpers return elapsed float and use deadline-aware sleep`.

## Scope (one commit)

Change only the two private async helpers; their consumer (`async_poll_branch_status`) currently `await`s them without using the return value, so changing the return type is backwards-compatible at this stage.

## WHERE

| File | Change |
|------|--------|
| `src/mcp_workspace/checks/branch_status.py` | Modify `_wait_for_ci` and `_wait_for_pr` |
| `tests/checks/test_branch_status_polling.py` | Update existing helper tests; add new tests |

## WHAT

New signatures:

```python
async def _wait_for_ci(project_dir: Path, branch_name: str, timeout: int) -> float
async def _wait_for_pr(project_dir: Path, branch_name: str, timeout: int) -> float
```

Both return elapsed seconds (`time.monotonic() - start`) on every exit path: terminal state, timeout reached, 3-error abort, immediate `timeout <= 0` exit.

## HOW (integration)

- No new imports needed (`time` and `asyncio` already imported).
- No callers updated; `async_poll_branch_status` keeps `await`-ing without using the value (Step 3 wires the value).
- Mypy `-> float` ↔ caller `await` with no assignment is fine — discarded return values are not flagged.

## ALGORITHM (deadline-aware sleep, applied identically to both helpers)

```
start    = time.monotonic()
deadline = start + timeout
errors   = 0
loop:
    if time.monotonic() >= deadline: return time.monotonic() - start
    try poll → terminal? return time.monotonic() - start
    except: errors += 1; if errors >= 3: return time.monotonic() - start
    remaining = deadline - time.monotonic()
    if remaining <= 0: return time.monotonic() - start
    await asyncio.sleep(min(_POLL_INTERVAL, remaining))
```

Replace the existing unconditional `await asyncio.sleep(_POLL_INTERVAL)` with the `min(_POLL_INTERVAL, remaining)` pattern. Make sure each `return` path computes `time.monotonic() - start`.

## DATA

- Return: `float` (elapsed seconds, always ≥ 0).
- No new constants. `_CI_POLL_INTERVAL = 15` and `_PR_POLL_INTERVAL = 20` unchanged.
- `_DEFAULT_PR_TIMEOUT` and `_MAX_CONSECUTIVE_ERRORS` unchanged in this step.

## Tests (in `tests/checks/test_branch_status_polling.py`)

Update existing helper tests:

- `TestWaitForCI.test_returns_immediately_on_success` — assert returned value is a `float` and ≈ 0.
- `TestWaitForCI.test_returns_immediately_on_failure` — same.
- `TestWaitForCI.test_timeout_zero_returns_immediately` — assert returned value is `0.0` (or near-zero float).
- `TestWaitForPR.test_returns_immediately_when_pr_found` — assert returned `float`.
- `TestWaitForPR.test_timeout_zero_returns_immediately` — assert returned `0.0`.

Add two new tests (deadline-aware sleep):

- `test_ci_deadline_aware_sleep_caps_at_remaining_time`:
  ```
  ci_timeout=5; mock get_latest_ci_status returns "in_progress"; mock asyncio.sleep with AsyncMock;
  await _wait_for_ci(...);
  for every call to mock_sleep, assert call_args[0][0] <= 5.0  (never the full 15s _CI_POLL_INTERVAL when remaining < 15).
  ```
- `test_pr_deadline_aware_sleep_caps_at_remaining_time`:
  ```
  pr_timeout=5; analogous with _wait_for_pr; assert sleep argument <= 5.0  (never the full 20s _PR_POLL_INTERVAL).
  ```

Tip: drive `time.monotonic` with a `side_effect` iterator so the loop runs at least once, then exits.

## Definition of Done

- All three quality checks pass.
- `_wait_for_ci` and `_wait_for_pr` return `float` on every path.
- No call to `asyncio.sleep` exceeds the remaining-deadline window.
- One commit produced.
