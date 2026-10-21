# Step 5 — Re-read `unstable` once, then look up checks, in `collect_branch_status`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md` exactly.
> Precondition: `PullRequestManager.get_non_green_checks` exists (step 3) and `BranchStatusReport`
> has `non_green_checks` / `non_green_checks_error` (step 4). If either is missing, write one line
> to `pr_info/.blocked.txt` and stop.
> TDD: write `tests/checks/test_branch_status_unstable_recheck.py` first, see it fail, then change
> the code. Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy; all must pass. Run
> `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/checks/branch_status.py` — constant, `_recheck_unstable`, wiring in `collect_branch_status`
- New: `tests/checks/test_branch_status_unstable_recheck.py`

## WHAT

```python
import time

# GitHub computes mergeable_state lazily; one re-read after this delay.
_UNSTABLE_REREAD_DELAY_SECONDS = 5.0

def _recheck_unstable(
    pr_manager: Optional[PullRequestManager],
    ci_status: CIStatus,
    pr_number: Optional[int],
    pr_mergeable: Optional[bool],
    pr_mergeable_state: Optional[str],
) -> tuple[Optional[bool], Optional[str], Optional[tuple[str, ...]], Optional[str]]: ...
```

## HOW

- In `collect_branch_status`, add a new step 9b directly after step 9 (`_collect_pr_info`) and
  before step 10 (`_apply_pr_merge_override`):

  ```python
  # 9b. Re-read a possibly stale "unstable" and look up non-green checks
  pr_mergeable, pr_mergeable_state, non_green_checks, non_green_checks_error = (
      _recheck_unstable(pr_manager, ci_status, pr_number, pr_mergeable, pr_mergeable_state)
  )
  ```

- Add `"non_green_checks"` and `"non_green_checks_error"` to `report_data`, and pass both to
  `BranchStatusReport(...)`.
- Blocking `time.sleep` is safe: `collect_branch_status` runs in `asyncio.to_thread`.
- Tests patch `mcp_workspace.checks.branch_status.time.sleep` (same pattern as
  `_pr_feedback_sources` tests), so no real 5 s sleeps.
- After the change, `branch_status.py` must be at most 750 lines (CI file-size limit; check with
  `check_file_size(max_lines=750)`). If it is over, write one line to `pr_info/.blocked.txt` and stop.

## ALGORITHM

```
if pr_manager is None or pr_number is None or pr_mergeable_state != "unstable" \
        or ci_status not in (CIStatus.PASSED, CIStatus.NOT_CONFIGURED):
    return pr_mergeable, pr_mergeable_state, None, None
time.sleep(_UNSTABLE_REREAD_DELAY_SECONDS); head_sha = None
try:
    pr = pr_manager.get_pull_request(pr_number)
    head_sha = pr.get("head_sha") if isinstance(pr.get("head_sha"), str) else None
    state = pr.get("mergeable_state")
    if isinstance(state, str) and state and state != "unknown":
        pr_mergeable, pr_mergeable_state = pr.get("mergeable"), state
except Exception:  # pylint: disable=broad-exception-caught  — every error keeps "unstable"
    logger.debug("PR re-read failed", exc_info=True)
if pr_mergeable_state != "unstable": return pr_mergeable, pr_mergeable_state, None, None
names, error = pr_manager.get_non_green_checks(pr_number, head_sha)
return pr_mergeable, pr_mergeable_state, names, error
```

The acceptance rule (a non-empty `str` other than `"unknown"`) is what stops a re-read from ever
turning `unstable` into `Ready to merge`, whether it returns `unknown`, `None`, `{}` or a bare `MagicMock`.

## DATA

Returns `(pr_mergeable, pr_mergeable_state, non_green_checks, non_green_checks_error)`. On the
untouched path these are the inputs unchanged plus `None, None`. The re-read values feed step 10
and the report.

## Tests (write first)

Use a fixture that patches the collaborators of `collect_branch_status` in `mcp_workspace.checks.branch_status`:

- `get_current_branch_name` → `"338-x"`
- `IssueManager` → MagicMock with `get_issue` → `{"number": 338, "labels": []}`
- `PullRequestManager` → a `pr_mgr` MagicMock
- `detect_base_branch` → `"main"`
- `_collect_linked_branch_status` → `(LinkedBranchStatus.OK, ("338-x",), 338, None)`
- `_collect_rebase_status` → `(False, "up-to-date")`
- `_collect_task_status` → `(TaskTrackerStatus.N_A, "No pr_info folder found", False)`
- `collect_pr_feedback` → `(None, False, False)`
- `get_default_branch_name` → `"main"`
- `time.sleep`

Parametrize `_collect_ci_status` and `_collect_pr_info`. The fixture yields `pr_mgr` and the sleep
mock. Always set `pr_mgr.get_pull_request.return_value` / `pr_mgr.get_non_green_checks.return_value` explicitly.

1. PASSED + `unstable`, re-read `clean` (`mergeable=True`) → `get_pull_request` called exactly once;
   `sleep` called once with `5.0`; lookup not called; `Ready to merge (squash-merge safe)` in recommendations.
2. NOT_CONFIGURED + `unstable`, re-read still `unstable` with `head_sha="abc"` → lookup called with `(45, "abc")`.
3. PASSED + still `unstable`, lookup returns names → names recommendation; `Non-green checks:`
   line in `format_for_human()` and `format_for_llm()`.
4. PASSED + still `unstable`, lookup `((), None)` → "likely stale, re-check"; `Ready to merge` never shown.
5. Re-read returns `{"mergeable_state": "unknown"}`, `{"mergeable_state": None}`, and `{}` (parametrize)
   → state stays `unstable`, lookup runs (with `head_sha=None` for `{}`), no `Ready to merge`.
6. Re-read raises `GithubException(403, ...)`, a rate-limit `GithubException`, and `RuntimeError`
   (parametrize) → state stays `unstable`, lookup runs with `head_sha=None`, and the report is intact
   (`branch_name == "338-x"`, `pr_number == 45`; not `create_empty_report`).
7. Lookup returns `((), "<reason>")` for a permission text, a rate-limit text, and an API-error text
   (parametrize) → the matching "could not list checks: …" recommendation, a `Non-green checks: lookup failed — …`
   line, and the report is intact.
8. No extra requests (parametrize): PASSED+`clean`, NOT_CONFIGURED+`clean`, FAILED+`unstable`,
   PASSED+`blocked` → `get_pull_request`, `get_non_green_checks` and `sleep` not called. The
   FAILED+`unstable` case keeps `Not ready to merge (GitHub mergeable_state: unstable)`.

The existing `test_issue_207_continue_on_error_scenario` and all other `tests/checks` tests must
pass unchanged.
