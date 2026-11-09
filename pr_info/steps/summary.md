# Summary — #382 check_branch_status attributes failed jobs to the wrong CI run

## Problem

When one commit has several CI runs, `build_ci_error_details` links every failed job to the
newest run (`run_data["url"]`, which is `first_run.html_url`), builds job links as
`{run_url}/job/{id}`, and merges all runs' logs into one dict keyed by filename, so a
same-named job in two runs shows one run's log for both.

## Architectural / design changes

- **Each job carries its own run context.** `JobData` gets three required keys:
  - `html_url`: the job's own URL from `WorkflowJob.html_url`
  - `run_html_url`: its run's `html_url`
  - `run_event`: its run's `event`

  All three come from objects `get_latest_ci_status` already loads, so there are no extra
  API requests. `RunData` and `caching/pull_requests.py` are unchanged.
- **Job links come from the API, not string building.** All three job-link sites in
  `ci_log_parser.py` use `job["html_url"]`, so a link always names the run that contains
  the job.
- **Logs are kept per run.** `logs.update(...)` becomes `logs_by_run: dict[int, dict[str, str]]`.
  Each job reads only its own run's logs. Runs past the 3-run fetch cap get `{}`, which
  falls through to the existing logs-unavailable text.
- **Run headers are printed only for runs with a placed job, within one flat loop.** Failed
  jobs are stable-sorted into run order (the order runs first appear, which is newest first).
  The existing single loop emits `GitHub Actions: <run_html_url>` before the first job of a
  run that gets a full section. The header's 2 lines are charged to that job's budget; if
  header plus job don't fit, the job goes to Other failed jobs. The same code path handles
  one run, so the single-run layout is unchanged and its header now uses the failed run's
  URL instead of `run_data["url"]`.
- **Event tags appear only when failures span runs.** With more than one failed run, each
  job gets the label `name (event)`. The label is used in run headers (event only), in the
  `Failed jobs (N):` summary and in the Other failed jobs list. With one run, nothing is
  tagged.
- **Truncated jobs are stored as `(label, step_name)` tuples.** The Other failed jobs section
  no longer looks jobs up by name, so the first-same-named-job-wins bug is gone.
- **Line budget fix.** The summary placeholder prints 3 lines; it is now charged 3, not 2.
- `run_data` is now only read for `jobs_fetch_warning` in `build_ci_error_details`.
  `CI=FAILED` logic (`aggregate_conclusion`) is untouched.

## Files modified

| File | Change |
|---|---|
| `src/mcp_workspace/github_operations/ci_results_manager.py` | `JobData` +3 keys; filled in `get_latest_ci_status` |
| `src/mcp_workspace/github_operations/ci_log_parser.py` | `build_ci_error_details`: per-run logs, job URLs, run headers, labels, budget fix |
| `tests/github_operations/test_ci_results_manager_status.py` | mock jobs set `html_url`; assert it is carried |
| `tests/github_operations/test_ci_results_manager_aggregation.py` | `_make_mock_job` sets `html_url`; `test_jobs_carry_run_id` asserts run URL/event |
| `tests/github_operations/test_ci_results_manager_foundation.py` | typed `CIStatusData` literal gets the 3 keys |
| `tests/github_operations/test_ci_log_parser.py` | job dicts get the 3 keys; new multi-run, budget and exact-output tests |

No files or folders are created (besides these plan files).

## Steps

1. `step_1.md`: `JobData` carries `html_url`, `run_html_url`, `run_event` (data model plus fixtures).
2. `step_2.md`: `build_ci_error_details` attributes links, logs and headers to each job's own run.

## Out of scope

- `cancelled` / `timed_out` jobs getting no section (separate issue).
- `caching/pull_requests.py` `_fetch_ci_status` newest-run URL (no job links there).
