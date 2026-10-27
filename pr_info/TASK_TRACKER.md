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

### Step 1: Query alerts by PR, `AlertData` shape, new alert line
See [step_1.md](./steps/step_1.md)

- [x] Implementation: tests first (mixin fixtures + exact request params, `_alert()` helper, `TestAlerts` lines), then `AlertData` in `pr_types.py`, `fetch_code_scanning_alerts` query by `pr`/`state`/`per_page`, new `[alert]` line in `checks/pr_feedback.py`
- [x] Quality checks: pylint, pytest, mypy, vulture — fix all issues
- [x] Commit message prepared

### Step 2: 403/404 on alerts → `skipped`, rendered as "alerts not checked"
See [step_2.md](./steps/step_2.md)

- [ ] Implementation: tests first (parametrized `test_code_scanning_error_routing`, `skipped == {}` asserts, `TestSkipped`, undeterminable/blocks-merge tests), then `PRFeedback.skipped`, fetch raises all errors, mixin routes 403/404 (non-rate-limit) to `skipped`, formatter clean-line note and `[skipped]` lines
- [ ] Quality checks: pylint, pytest, mypy, vulture — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
