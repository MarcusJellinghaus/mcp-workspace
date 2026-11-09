# Step 2 — `build_ci_error_details` attributes links, logs and headers to each job's own run

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md` exactly.
> Write the tests first, then change `build_ci_error_details`. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`) and mypy via the MCP tools; all must pass. Make one commit.

## Precondition

`JobData` in `src/mcp_workspace/github_operations/ci_results_manager.py` has `html_url`,
`run_html_url` and `run_event` (step 1). If not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/ci_log_parser.py`: `build_ci_error_details` only
- `tests/github_operations/test_ci_log_parser.py`: `TestBuildCiErrorDetails`

## WHAT

Signature unchanged:

```python
def build_ci_error_details(
    ci_manager: "CIResultsManager",
    status_result: Mapping[str, object],
    max_lines: int = 300,
) -> str | None
```

No new helpers. Keep the existing single job loop. Only extract a helper if pylint reports
too-many-locals/branches/statements.

## HOW / ALGORITHM

```
failed_jobs = [j for j in jobs if conclusion == "failure"]
run_keys = list(dict.fromkeys(j.get("run_id") or 0 for j in failed_jobs))   # newest first
failed_jobs.sort(key=lambda j: run_keys.index(j.get("run_id") or 0))         # stable: group by run
multi_run = len(run_keys) > 1
logs_by_run = {rid: get_run_logs(rid) for rid in [k for k in run_keys if k][:3]}  # keep try/except per rid
for job: label = f"{name} ({event})" if multi_run else name
         needs_header = run_html_url and run_key != last_header_run ; header_cost = 2 if needs_header else 0
         remaining = max_lines - lines_used - header_cost - job_header_lines - 5
         if remaining <= 10: truncated.append((label, step_name)); continue
         if needs_header: emit "GitHub Actions: {run_html_url}" + (f" ({event})" if multi_run) and ""; last_header_run = run_key
         emit job section; lines_used += header_cost + job_header_lines + len(log_lines) + 1; shown.append(label)
```

Details:

1. **Remove** `run_url = str(run_data.get("url", ""))` and the upfront `GitHub Actions:` block
   (~:321-325). `run_data` stays only for `jobs_fetch_warning`.
2. **Logs:** replace `logs: dict[str, str]` and `logs.update(...)` with
   `logs_by_run: dict[int, dict[str, str]]`. Keep the existing try/except and warning per run id.
   In the loop: `_find_log_content(logs_by_run.get(run_key, {}), job_name, step_number, step_name)`.
   Keep the fetch before the `if not failed_jobs: return None` check, as today.
3. **Budget fix:** the summary placeholder adds `lines_used += 3` (it prints 3 lines).
4. **Job URL:** `job_url = str(job.get("html_url") or "")`, then:
   - `has_job_url = bool(job_url)`
   - `View on GitHub: {job_url}`
   - `View job: {job_url}`

   Delete the `job_id` usage.
5. **Per job:** `run_key = job.get("run_id") or 0`, `run_url = str(job.get("run_html_url") or "")`,
   `event = str(job.get("run_event") or "")`. Initialise `last_header_run: int | None = None`
   before the loop.
6. **Truncated list:** `jobs_truncated: list[tuple[str, str]]` of `(label, step_name)`.
   The Other failed jobs section becomes
   `for label, step in jobs_truncated: output_lines.append(f'- {label}: step "{step}" failed')`.
   Delete the name lookup loop (~:409-421).
7. **Summary:** `all_failed = jobs_shown + [label for label, _ in jobs_truncated]`. Format unchanged.

## DATA

The return value is still `str | None`. Output for one failed run is unchanged:
- one header, no event
- `Failed jobs (N): a, b`
- `- a: step "X" failed`

Output for several failed runs:

```
## CI Failure Summary
Failed jobs (2): ruff (pull_request), test (push)

GitHub Actions: <run B url> (pull_request)

## Job: ruff
View job: <job url in run B>
...

GitHub Actions: <run A url> (push)

## Job: test
...
## Other failed jobs (logs omitted — raise max_log_lines to include them)
- lint (push): step "X" failed
```

## Tests (write first)

**Fixture update:** every failed-job dict in `TestBuildCiErrorDetails` gets:
- `"html_url": f"{run_url}/job/{id}"`
- `"run_html_url"`: the URL already used in that test's `status["run"]["url"]`
- `"run_event": "push"`

`test_limits_run_ids_to_three` keeps `run_id=0` for one job and must still call
`get_run_logs` 3 times.

**Exact single-run output.** Add `test_single_run_output_exact` first and run it before
changing the code; it must pass on the unchanged code. If it fails there, write one line to
`pr_info/.blocked.txt` and stop.
- Inputs:
  - run URL `R = "https://github.com/org/repo/actions/runs/123"`, used as `status["run"]["url"]`
    and as the job's `run_html_url`
  - one failed job: `name="test-job"`, `id=456`, `run_id=123`, `html_url=f"{R}/job/456"`,
    `run_event="push"`, step `{"name": "Run tests", "number": 3, "conclusion": "failure"}`
  - logs `{"0_test-job.txt": "2024-01-15T10:30:45.1234567Z Error: test failed"}`
- Expected:

  ```python
  "## CI Failure Summary\nFailed jobs (1): test-job\n\n"
  f"GitHub Actions: {R}\n\n"
  "## Job: test-job\n"
  f"View job: {R}/job/456\n"
  "Failed step: Run tests\n\n"
  "Error: test failed\n"
  ```

**New tests.** `get_run_logs` uses `side_effect=lambda rid: {...}` where per-run logs matter.
Run A = `.../runs/100`, event `push` (older). Run B = `.../runs/200`, event `pull_request`
(newer, listed first in `jobs`).

1. `test_failed_job_in_older_run_links_to_its_run`
   - Setup: B has only a successful job; A has failed job `ruff` (id 1001,
     `html_url=f"{A}/job/1001"`); `status["run"]["url"] = B`.
   - Assert:
     - `f"GitHub Actions: {A}\n"` is in the result, with no `(push)`
     - `f"View job: {A}/job/1001"` is in the result
     - `B` is not in the result
2. `test_failed_jobs_in_two_runs_grouped_by_run`
   - Setup: B fails `lint`, A fails `test`.
   - Assert this order by index: `GitHub Actions: {B} (pull_request)` < `## Job: lint` <
     `GitHub Actions: {A} (push)` < `## Job: test`.
   - Assert the summary `Failed jobs (2): lint (pull_request), test (push)`.
3. `test_same_named_job_shows_own_run_log`
   - Setup: job `test` fails in both runs; the logs are `{"0_test.txt": f"log from run {rid}"}`.
   - Assert: `log from run 200` appears after B's header and before A's header, and
     `log from run 100` appears after A's header.
4. `test_job_beyond_log_cap_has_correct_link`
   - Setup: 4 runs (ids 1-4), each with one failed job `job-{rid}`, `html_url=f".../runs/{rid}/job/{rid}"`.
   - Assert:
     - `get_run_logs.call_count == 3`
     - the result has `GitHub Actions: .../runs/4 (push)`, `View on GitHub: .../runs/4/job/4`
       and `(logs not available locally)` in run 4's section
5. `test_same_named_jobs_in_other_failed_jobs_tagged_by_event`
   - Setup: job `test` fails in B at step `Step B` and in A at step `Step A`, `max_lines=15`.
   - Assert:
     - `- test (pull_request): step "Step B" failed` and `- test (push): step "Step A" failed`
       are both present
     - `"GitHub Actions:"` is not in the result
     - the summary reads `Failed jobs (2): test (pull_request), test (push)`
6. `test_run_header_charged_to_first_job_budget`
   - Setup: one run, one failed job with `html_url` and no logs.
   - Assert:
     - `max_lines=24`: the job is listed under Other failed jobs and `"GitHub Actions:"` is
       absent. This fails on the old code, which placed it.
     - `max_lines=25`: the header and `## Job:` section are present.

Existing tests (`test_truncates_long_output`, `test_per_job_line_budget_truncation`,
`test_both_marker_sites_use_one_spelling`, `test_run_url_in_output`) must pass unchanged
apart from the fixture keys.

## Done when

pylint, pytest and mypy pass; one commit, e.g.
`fix(ci): attribute failed jobs, links and logs to their own CI run (#382)`.
