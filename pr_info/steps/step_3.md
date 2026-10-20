# Step 3 — wire `lookup_error` into `CIStatusData` / `get_latest_ci_status`

Reference: `pr_info/steps/summary.md` for full context and architecture. This step
implements summary points 3 and 4, tying together steps 1 and 2.

## Precondition

Read `src/mcp_workspace/github_operations/ci_results_manager.py`. If `CIStatusData`
already defines `lookup_error`, write one line to `pr_info/.blocked.txt` and stop.
This step requires step 1's `on_error` parameter and step 2's
`_last_repository_error` attribute to already exist in `base_manager.py` — if either
is missing, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/ci_results_manager.py` — `CIStatusData`,
  `get_latest_ci_status`, new module-level helper `_set_lookup_error`
- `tests/github_operations/test_ci_results_manager_status.py` — class
  `TestLookupFailedFlag` (extend)

## WHAT

```python
class CIStatusData(TypedDict):
    run: RunData
    jobs: List[JobData]
    lookup_failed: NotRequired[bool]
    lookup_error: NotRequired[str]


def _set_lookup_error(e: BaseException, data: CIStatusData) -> None:
    ...
```

`_set_lookup_error` is passed as `on_error` to the `@_handle_github_errors` decorator
on `get_latest_ci_status` (covers the swallowed-exception path). The
`_get_repository()`-returns-`None` branch sets `lookup_error` directly from
`self._last_repository_error` instead, since that failure never reaches the
decorator's except clauses.

## HOW

Update the decorator:

```python
@_handle_github_errors(
    default_return=lambda: CIStatusData(run={}, jobs=[], lookup_failed=True),  # type: ignore[typeddict-item]
    on_error=_set_lookup_error,
)
```

Update the manual early return when `repo` is falsy:

```python
if not repo:
    logger.error("Could not access GitHub repository")
    data = CIStatusData(run={}, jobs=[], lookup_failed=True)  # type: ignore[typeddict-item]
    if self._last_repository_error is not None:
        data["lookup_error"] = self._last_repository_error
    return data
```

No change to the "no workflow runs found" branch (`CIStatusData(run={}, jobs=[])`) —
that is not a failure; `lookup_failed`/`lookup_error` are not set there.

## ALGORITHM (`_set_lookup_error`)

```
if isinstance(e, GithubException):
    message = e.data.get("message", "") if isinstance(e.data, dict) else ""
    data["lookup_error"] = f"GitHub API error {e.status}: {message}"
else:
    data["lookup_error"] = f"network error: {type(e).__name__}"
```

## DATA

`CIStatusData.lookup_error: NotRequired[str]` — present only when `lookup_failed` is
`True`; absent on every success path.

## Tests (write first)

Extend `TestLookupFailedFlag` in `tests/github_operations/test_ci_results_manager_status.py`:

- `test_lookup_error_set_on_swallowed_429_github_exception` —
  `mock_repo.get_workflow_runs.side_effect = GithubException(429, {"message": "rate limited"}, {})`;
  assert `result["lookup_error"] == "GitHub API error 429: rate limited"`.
- `test_lookup_error_set_on_swallowed_generic_exception` —
  `mock_repo.get_workflow_runs.side_effect = RuntimeError("boom")`; assert
  `result["lookup_error"] == "network error: RuntimeError"`.
- `test_lookup_error_set_from_last_repository_error_when_repo_inaccessible` — set
  `ci_manager._last_repository_error = "GitHub API error 500: down"` before patching
  `_get_repository` to return `None`; assert
  `result["lookup_error"] == "GitHub API error 500: down"`.
- `test_lookup_error_absent_on_success` — alongside the existing
  `test_lookup_failed_absent_on_success`; assert `"lookup_error" not in result`.
- `test_lookup_error_excludes_token_and_headers` — assert the produced string never
  contains the configured token or a header value, for both the `GithubException`
  and generic `Exception` cases.

## Commit

One commit: tests plus the `ci_results_manager.py` change. Run pytest (`-n auto`),
pylint, mypy — all must pass. Format, stage, commit.

## LLM Prompt

Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md` exactly:
add `lookup_error: NotRequired[str]` to `CIStatusData`, add the `_set_lookup_error`
helper, wire it as `on_error` into the `@_handle_github_errors` decorator on
`get_latest_ci_status`, and populate `lookup_error` from
`self._last_repository_error` on the `_get_repository()`-None branch, all in
`src/mcp_workspace/github_operations/ci_results_manager.py`. Write the tests listed
under "Tests (write first)" in
`tests/github_operations/test_ci_results_manager_status.py` first, then the
implementation. Run pytest/pylint/mypy, format, and commit as one commit. This is
the final step — steps 1 and 2 (`base_manager.py` changes) must already be present.
