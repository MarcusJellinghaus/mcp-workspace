# Summary — Issue #318: CI status collection misreports transient errors and stale runs

## Problem

`_collect_ci_status` and `_wait_for_ci` cannot distinguish "no CI configured" from
"the CI lookup failed" (both currently read as an empty `run`), and neither compares
the returned run's `commit_sha` to the commit actually under test — so a stale run
from the previous push is reported as the result for the new one.

## Architectural / design changes

1. **`CIStatusData` gains an optional `lookup_failed: NotRequired[bool]` flag.**
   Set only on the two paths that mean "we don't actually know the CI state":
   the `_handle_github_errors` default-return factory on `get_latest_ci_status`,
   and the `_get_repository()`-failed early return inside it. A genuinely empty
   `run` (no workflow configured) never sets it.

2. **One new low-level git helper: `get_remote_branch_commit_sha`** in
   `git_operations/branch_queries.py`, next to the existing `remote_branch_exists`
   (same repo-open / origin-remote / ref-lookup shape, now returning a commit sha
   instead of a bool). No new module — this is a one-function addition reusing an
   existing file's conventions.

3. **One new pure predicate: `_is_stale_ci_run`** in `checks/branch_status.py`,
   shared by `_collect_ci_status` and `_wait_for_ci` (the issue's "one shared
   sha-check helper" requirement). It compares the run's `commit_sha` to local
   HEAD (`get_latest_commit_sha`), but only when local HEAD equals
   `origin/<branch>` (via the new helper above) — otherwise it returns `False`
   ("skip the check"), which both callers already treat the same as "not stale".
   No tristate/enum: both "fresh" and "skipped" collapse to one boolean because
   no caller needs to distinguish them.

4. **`_collect_ci_status` changes (minimal diff, no new branches beyond the two
   above):**
   - The existing empty-`run` guard gains one nested check: `lookup_failed` →
     `CIStatus.UNKNOWN`; otherwise unchanged (`CIStatus.NOT_CONFIGURED`).
   - Immediately after that guard, a non-empty but stale run short-circuits to
     `CIStatus.PENDING` before conclusion/status is ever inspected.
   - The bottom `except Exception` now returns `CIStatus.UNKNOWN` instead of
     `CIStatus.NOT_CONFIGURED` (this is why `NOT_CONFIGURED` stops being
     `ci_ok` for error cases — intended, see issue Constraints).

5. **`_generate_recommendations` gains one `elif` branch** for `CIStatus.UNKNOWN`
   ("CI status could not be determined — retry"). `ci_ok` already excludes
   `UNKNOWN`, so "Ready to merge" still never fires for it.

6. **`_wait_for_ci` changes by augmenting one existing condition, not adding a
   branch:** the "terminal run" check gains `and not _is_stale_ci_run(...)`.
   A stale terminal run now falls through to the existing sleep/retry path
   instead of returning early. `lookup_failed` results already fall through
   today (the returned `run` is `{}`, which is falsy) — this gets a pinning
   test, not new code.

No new source files, no new modules, no new abstractions beyond the two small
functions in (2) and (3).

## Files / modules touched

**Modified:**
- `src/mcp_workspace/github_operations/ci_results_manager.py`
- `src/mcp_workspace/git_operations/branch_queries.py`
- `src/mcp_workspace/checks/branch_status.py`
- `src/mcp_workspace/checks/branch_status_polling.py`
- `tests/github_operations/test_ci_results_manager_status.py`
- `tests/git_operations/test_branch_queries.py`
- `tests/checks/test_branch_status_ci.py`
- `tests/checks/test_branch_status_recommendations.py`
- `tests/checks/test_branch_status_polling.py`

**Created:**
- `tests/checks/test_branch_status_sha_check.py`

## Steps (one commit each, TDD: tests first, then implementation, in the same commit)

1. `step_1.md` — `lookup_failed` flag on `CIStatusData` (`ci_results_manager.py`)
2. `step_2.md` — `get_remote_branch_commit_sha` helper (`branch_queries.py`)
3. `step_3.md` — `_is_stale_ci_run` predicate (`branch_status.py`)
4. `step_4.md` — wire `lookup_failed` + staleness into `_collect_ci_status`
5. `step_5.md` — `UNKNOWN` branch in `_generate_recommendations`
6. `step_6.md` — staleness guard in `_wait_for_ci` (`branch_status_polling.py`)

Steps 1–3 are independent building blocks; steps 4–6 wire them in and must follow
in that order (4 needs 1 and 3; 6 needs 3).

## Quality gates (every step)

After writing the implementation for a step, run and ensure all pass:
`mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check`
(with `extra_args: ["-n", "auto"]`), `mcp__mcp-tools-py__run_mypy_check`. Then
run `mcp__mcp-tools-py__run_format_code` before committing.
