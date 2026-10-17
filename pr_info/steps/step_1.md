# Step 1 — `lookup_failed` flag on `CIStatusData`

Read `pr_info/steps/summary.md` first for overall context. This step implements
design change (1) from that summary, in isolation from the rest.

## Precondition

None beyond the repo being in its current state (`CIStatusData`, `get_latest_ci_status`,
and `_get_repository()` exist as described below). If
`src/mcp_workspace/github_operations/ci_results_manager.py` does not contain a
`get_latest_ci_status` method decorated with `_handle_github_errors`, write one
line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/ci_results_manager.py` (modify)
- `tests/github_operations/test_ci_results_manager_status.py` (modify — add tests)

## WHAT

- `CIStatusData` (TypedDict): add one field `lookup_failed: NotRequired[bool]`.
- No new functions. Two existing return sites change:
  1. The decorator on `get_latest_ci_status`:
     `@_handle_github_errors(default_return=CIStatusData(run={}, jobs=[]))` →
     a zero-arg factory so each failure gets a fresh dict:
     `@_handle_github_errors(default_return=lambda: CIStatusData(run={}, jobs=[], lookup_failed=True))`
     Keep the existing `# type: ignore[typeddict-item]` comment on that line.
  2. Inside `get_latest_ci_status`, the `if not repo:` early return:
     `return CIStatusData(run={}, jobs=[])  # type: ignore[typeddict-item]` →
     `return CIStatusData(run={}, jobs=[], lookup_failed=True)  # type: ignore[typeddict-item]`

## HOW

- No new imports needed — `NotRequired` is already imported from `typing_extensions`.
- `_handle_github_errors` in `base_manager.py` already supports a callable
  `default_return` (factory form): `resolved = default_return() if callable(default_return) else default_return`.
  Do not modify `base_manager.py`.
- Every other `@_handle_github_errors(...)` call site in this file and elsewhere
  is untouched — this flag is specific to `get_latest_ci_status`.

## ALGORITHM

Not applicable — this is a data-shape change plus two literal edits, no new logic.

## DATA

`CIStatusData` becomes:
```python
class CIStatusData(TypedDict):
    run: RunData
    jobs: List[JobData]
    lookup_failed: NotRequired[bool]
```
`lookup_failed` is `True` only on the decorator's default return and the
`_get_repository()` failure path; absent (not `False`) on every other return,
including the genuine "no workflow runs found" early return
(`return CIStatusData(run={}, jobs=[])  # type: ignore[typeddict-item]` right
after `except IndexError` — leave that one unchanged).

## Tests to write first (TDD)

In `tests/github_operations/test_ci_results_manager_status.py`, add a test class
(e.g. `TestLookupFailedFlag`) using the existing `mock_repo` / `ci_manager`
fixtures already present in that file:

1. `test_lookup_failed_set_on_non_auth_github_exception` — set
   `mock_repo.get_workflow_runs.side_effect = GithubException(500, "boom", {})`,
   call `ci_manager.get_latest_ci_status("main")`, assert
   `result["run"] == {}` and `result.get("lookup_failed") is True`.
2. `test_lookup_failed_set_on_generic_exception` — same, but
   `side_effect = RuntimeError("boom")`.
3. `test_lookup_failed_set_when_repository_inaccessible` — patch/force
   `_get_repository()` to return `None` for this call (e.g. patch
   `ci_manager._get_repository` to `return_value=None`), call
   `get_latest_ci_status("main")`, assert `lookup_failed is True`.
4. `test_lookup_failed_absent_on_success` — reuse an existing happy-path mock
   setup from this file (a successful run), assert
   `"lookup_failed" not in result`.

Run these against the *current* code first to confirm 1–3 fail (field doesn't
exist / isn't set) and 4 passes, then implement the change above and confirm
all four pass.

## Commit

One commit: tests + implementation + green checks.
Message: `feat(ci_results_manager): mark lookup failures with lookup_failed flag`
