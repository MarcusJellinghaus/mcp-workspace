# Step 1 — `JobData` carries the job URL and its run's URL and event

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md` exactly.
> Write or extend the tests first, then change the code. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`) and mypy via the MCP tools; all must pass. Make one commit.

## WHERE

- `src/mcp_workspace/github_operations/ci_results_manager.py`: `JobData`, `get_latest_ci_status`
- `tests/github_operations/test_ci_results_manager_status.py`
- `tests/github_operations/test_ci_results_manager_aggregation.py`
- `tests/github_operations/test_ci_results_manager_foundation.py`

## WHAT

```python
class JobData(TypedDict):
    id: int
    run_id: int
    name: str
    status: str
    conclusion: str | None
    started_at: str | None
    completed_at: str | None
    steps: list[StepData]
    html_url: str        # job's own URL (WorkflowJob.html_url)
    run_html_url: str    # URL of the run containing this job
    run_event: str       # event of that run, e.g. "push", "pull_request"
```

All three are required keys (no `NotRequired`, no fallback). `RunData` is unchanged.

## HOW

In the `for job in run.jobs():` loop of `get_latest_ci_status`, add to the `job_data` dict:

```python
"html_url": job.html_url,
"run_html_url": run.html_url,
"run_event": run.event,
```

No new requests; `job.html_url` is part of the jobs list response already being iterated.

## Tests (write first)

- `test_ci_results_manager_status.py`
  - Every `Mock()` job in the file sets `html_url` to a string, e.g.
    `mock_job1.html_url = "https://github.com/test/repo/actions/runs/123456789/job/987654321"`.
  - In `test_successful_status_retrieval`, assert `job1_data["html_url"]` equals that string,
    `job1_data["run_html_url"] == mock_run.html_url` and `job1_data["run_event"] == "push"`.
- `test_ci_results_manager_aggregation.py`
  - `_make_mock_job` sets
    `mock_job.html_url = f"https://github.com/test/repo/actions/runs/0/job/{job_id}"`.
  - Extend `test_jobs_carry_run_id`. Build `run2` with `_make_mock_run(200, event="pull_request")`,
    then assert:
    - `test_job["run_html_url"] == run1.html_url` and `test_job["run_event"] == "push"`
    - `lint_job["run_html_url"] == run2.html_url` and `lint_job["run_event"] == "pull_request"`

    Check the `_make_mock_run` signature and default `event` first; adapt the keyword if it differs.
- `test_ci_results_manager_foundation.py` `test_cistatus_data_structure`: add the 3 keys to the
  job literal (`"html_url": "https://github.com/test/repo/actions/runs/123/job/456"`,
  `"run_html_url": "https://github.com/test/repo/actions/runs/123"`, `"run_event": "push"`),
  otherwise mypy strict fails.

## DATA

`get_latest_ci_status(...)["jobs"]` entries now include `html_url`, `run_html_url`,
`run_event` (all `str`). `run` dict unchanged.

## Done when

pylint, pytest and mypy pass; one commit, e.g.
`feat(ci): carry job URL and run URL/event on JobData (#382)`.
