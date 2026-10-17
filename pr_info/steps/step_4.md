# Step 4 — wire `lookup_failed` + staleness into `_collect_ci_status`

Read `pr_info/steps/summary.md` first for overall context. This step implements
design change (4) and depends on steps 1 and 3 being complete.

## Precondition

If `CIStatusData` does not have a `lookup_failed` field, or
`branch_status.py` does not have an `_is_stale_ci_run` function, write one
line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/checks/branch_status.py` (modify `_collect_ci_status` only)
- `tests/checks/test_branch_status_ci.py` (modify one test, add new tests)

## WHAT

Modify the existing `_collect_ci_status(project_dir, branch_name, max_log_lines)`
function body only. No signature change.

## HOW

No new imports (uses `_is_stale_ci_run` from step 3, already in this module).

Current code:
```python
run_data = status_result.get("run")

if run_data is None or len(run_data) == 0:
    return CIStatus.NOT_CONFIGURED, None, []
```
becomes:
```python
run_data = status_result.get("run")

if run_data is None or len(run_data) == 0:
    if status_result.get("lookup_failed"):
        return CIStatus.UNKNOWN, None, []
    return CIStatus.NOT_CONFIGURED, None, []

if _is_stale_ci_run(project_dir, branch_name, run_data.get("commit_sha")):
    return CIStatus.PENDING, None, []
```
(inserted before the existing `jobs_data = status_result.get("jobs", [])` line).

And the bottom of the function:
```python
except Exception:  # pylint: disable=broad-exception-caught
    logger.debug("CI status collection failed", exc_info=True)
    return CIStatus.NOT_CONFIGURED, None, []
```
becomes:
```python
except Exception:  # pylint: disable=broad-exception-caught
    logger.debug("CI status collection failed", exc_info=True)
    return CIStatus.UNKNOWN, None, []
```

## ALGORITHM

```
result = ci_manager.get_latest_ci_status(branch)
run = result["run"]
if run is empty:
    return UNKNOWN if result["lookup_failed"] else NOT_CONFIGURED
if _is_stale_ci_run(project_dir, branch, run["commit_sha"]):
    return PENDING
... existing conclusion/status handling, unchanged ...
except Exception: return UNKNOWN
```

## DATA

Return type unchanged: `tuple[CIStatus, Optional[str], List[str]]`. New
reachable values at the two changed sites: `(CIStatus.UNKNOWN, None, [])` and
`(CIStatus.PENDING, None, [])`.

## Tests to write first (TDD)

In `tests/checks/test_branch_status_ci.py`:

1. **Modify** `test_exception_returns_not_configured` → rename to
   `test_exception_returns_unknown`, change the assertion to
   `assert status == CIStatus.UNKNOWN`.
2. **Add** `test_lookup_failed_returns_unknown` — mock
   `mock_ci.get_latest_ci_status.return_value = {"run": {}, "jobs": [], "lookup_failed": True}`;
   assert `status == CIStatus.UNKNOWN`.
3. **Add** `test_stale_run_returns_pending` — mock
   `mock_ci.get_latest_ci_status.return_value = {"run": {"conclusion": "success", "status": "completed", "commit_sha": "old"}, "jobs": []}`;
   patch `mcp_workspace.checks.branch_status._is_stale_ci_run` to
   `return_value=True`; assert `status == CIStatus.PENDING` and that
   `build_ci_error_details` (if also patched/mocked) is not called.
4. **Add** `test_mismatched_sha_but_unpushed_head_keeps_current_behavior` —
   same run data as test 3 (`commit_sha="old"`, conclusion success) but do
   **not** patch `_is_stale_ci_run`; since the test calls
   `_collect_ci_status(Path("/tmp"), "main", 300)` and `/tmp` is not a
   resolvable git repo with a matching `origin/main`, the real
   `_is_stale_ci_run` returns `False` (check skipped) — assert
   `status == CIStatus.PASSED`, confirming existing tests using `Path("/tmp")`
   are unaffected by the new check.

All other existing tests in this file use `Path("/tmp")` and runs without a
`commit_sha` key (`run_data.get("commit_sha")` → `None`), so `_is_stale_ci_run`
short-circuits to `False` for them too — they should need no changes beyond
test 1's rename/assertion.

Confirm test 1's old assertion and tests 2–3 fail against current code, then
implement and confirm all pass (including the full existing file).

## Commit

One commit: tests + implementation + green checks.
Message: `fix(branch_status): surface lookup failures and stale CI runs correctly`
