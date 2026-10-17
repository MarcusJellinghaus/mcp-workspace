# Step 6 — staleness guard in `_wait_for_ci`

Read `pr_info/steps/summary.md` first for overall context. This step
implements design change (6) and depends on step 3 being complete
(`_is_stale_ci_run` must exist in `branch_status.py`).

## Precondition

If `src/mcp_workspace/checks/branch_status.py` does not export
`_is_stale_ci_run`, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/checks/branch_status_polling.py` (modify `_wait_for_ci` only)
- `tests/checks/test_branch_status_polling.py` (modify — add two tests)

## WHAT

No signature change to
`async def _wait_for_ci(project_dir: Path, branch_name: str, timeout: int) -> float`.

## HOW

Add one import line at the top of `branch_status_polling.py`:
```python
from mcp_workspace.checks.branch_status import _is_stale_ci_run
```
(this already imports `collect_branch_status` from the same module, so this
follows the existing pattern — `branch_status.py` does not import anything
back from `branch_status_polling.py`).

Current code inside the polling loop:
```python
            run = result.get("run") if isinstance(result, dict) else None
            if run and run.get("conclusion") in ("success", "failure"):
                logger.info("CI reached terminal state for branch=%s", branch_name)
                return time.monotonic() - start
```
becomes:
```python
            run = result.get("run") if isinstance(result, dict) else None
            if (
                run
                and run.get("conclusion") in ("success", "failure")
                and not _is_stale_ci_run(project_dir, branch_name, run.get("commit_sha"))
            ):
                logger.info("CI reached terminal state for branch=%s", branch_name)
                return time.monotonic() - start
```
No other lines change — a stale terminal run simply falls through to the
existing `remaining = deadline - time.monotonic()` / `asyncio.sleep(...)` tail
of the loop, exactly like the current `in_progress`/`queued` case.
`lookup_failed` results already fall through today (`run` is `{}`, which is
falsy) — no code change needed for that case, only a pinning test below.

## ALGORITHM

```
loop until deadline:
    result = get_latest_ci_status(branch)
    run = result.get("run")
    if run and run.conclusion in (success, failure) and not stale(run):
        return elapsed  # terminal and fresh
    # else: in_progress / stale / lookup_failed — keep polling
    sleep(min(poll_interval, remaining))
```

## DATA

No change to the function's return type (`float`, elapsed seconds). No new
data structures.

## Tests to write first (TDD)

In `tests/checks/test_branch_status_polling.py`, add to `TestWaitForCI`:

1. `test_stale_terminal_run_does_not_end_wait` — `ci_manager.get_latest_ci_status.return_value = {"run": {"conclusion": "success", "commit_sha": "old"}}`;
   patch `mcp_workspace.checks.branch_status_polling._is_stale_ci_run` to
   `return_value=True`; reuse the deadline-aware `time.monotonic` /
   `asyncio.sleep` mocking pattern already used in
   `test_returns_after_timeout_when_in_progress` (a `times` iterator feeding
   several values ending at/after the deadline) with `timeout=60`; assert
   `ci_manager.get_latest_ci_status.call_count > 1` (i.e. it kept polling
   instead of returning after the first call) and that `mock_sleep` was
   called.
2. `test_lookup_failed_keeps_polling` — `ci_manager.get_latest_ci_status.return_value = {"run": {}, "lookup_failed": True}`;
   same deadline-mocking pattern, `timeout=60`; assert
   `ci_manager.get_latest_ci_status.call_count > 1` and `mock_sleep` was
   called. This test should already pass against the *current* code (no
   staleness import needed for it to pass) — it documents existing behavior
   so it cannot silently regress.

Confirm test 1 fails against current code (returns after the first call
instead of polling), then implement the import + condition change and confirm
both tests pass, alongside the full existing file (`test_branch_status_polling.py`)
and `test_branch_status_polling_orchestrator.py`.

## Commit

One commit: tests + implementation + green checks.
Message: `fix(branch_status_polling): don't treat a stale CI run as terminal`
