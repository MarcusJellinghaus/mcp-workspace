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

### Step 1: `alert_skip_status` classifier; `_collect_pr_feedback` uses it
See [step_1.md](./steps/step_1.md)

- [x] Implementation: `test_alert_skip_status` tests + `alert_skip_status` in `_pr_feedback_sources.py`, `pr_feedback_mixin.py` routes on it, module docstring updated
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Move PR-cache test helpers into `_pr_cache_test_helpers.py` (pure refactor)
See [step_2.md](./steps/step_2.md)

- [x] Implementation: create `tests/github_operations/caching/_pr_cache_test_helpers.py`, import helpers in `test_pull_requests_results.py` (same test count)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: `AlertsResult`, `PullRequestCache.alerts()` slot, tests and docs
See [step_3.md](./steps/step_3.md)

- [x] Implementation: `test_pull_requests_alerts.py` tests + `AlertsResult` in `pr_types.py`, `alerts()` / `_alerts` in `caching/pull_requests.py`, README and release notes updated
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

## Pull Request

- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
