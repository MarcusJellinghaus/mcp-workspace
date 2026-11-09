# Task Status Tracker

## Instructions for LLM

This tracks **Feature Implementation** consisting of multiple **Tasks**.

**Summary:** See [summary.md](./steps/summary.md) for implementation overview.

**How to update tasks:**
1. Change [ ] to [x] when implementation step is fully complete (code + checks pass)
2. Change [x] to [ ] if task needs to be reopened
3. Add brief notes in the linked detail files if needed
4. Keep it simple - just GitHub-style checkboxes

**Task format:**
- [x] = Task complete (code + all checks pass)
- [ ] = Task not complete
- Each task links to a detail file in steps/ folder

---

## Tasks

### Step 1: `JobData` carries the job URL and its run's URL and event — [step_1.md](./steps/step_1.md)

- [x] Implementation: tests first (status, aggregation, foundation fixtures), then add `html_url`, `run_html_url`, `run_event` to `JobData` and fill them in `get_latest_ci_status`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `build_ci_error_details` attributes links, logs and headers to each job's own run — [step_2.md](./steps/step_2.md)

- [ ] Implementation: tests first (`test_single_run_output_exact` on unchanged code, fixture keys, 6 new multi-run/budget tests), then per-run logs, job URLs from `html_url`, per-run headers, event labels, `(label, step)` truncation list, budget fix in `build_ci_error_details`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main`; address any findings
- [ ] PR summary prepared (title + description covering the problem, design changes and tests)
