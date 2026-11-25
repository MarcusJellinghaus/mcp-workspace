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

### Step 1: Plugin skeleton, configure-time checks, guard 1, `time_limit` validation
See [step_1.md](./steps/step_1.md)

- [ ] Implementation: `tests/test_guards.py` collection/config tests, then `tests/_guards.py` (options, `pytest_configure`, collect-report wrapper), `tests/conftest.py` wiring, pyproject marker + `test_time_limits`, vulture whitelist, `time_limit` on candidate tests
- [ ] Quality checks (pylint, unit-group pytest, serial `tests/test_guards.py`, serial performance run, mypy, ruff, vulture) — fix all issues
- [ ] Commit message prepared

### Step 2: Git guard and shared call/teardown reporting
See [step_2.md](./steps/step_2.md)

- [ ] Implementation: `test_is_git` and `test_git_guard` first, then `Popen.__init__` counter, `_TestState`, `_report`, `_attach`, setup/call/teardown hooks, vulture whitelist, docstring; fix any existing unmarked git-starting tests
- [ ] Quality checks (pylint, unit-group pytest, serial `tests/test_guards.py`, serial performance run, mypy, ruff, vulture) — fix all issues
- [ ] Commit message prepared

### Step 3: Per-group time limits, documentation, final unit-group run
See [step_3.md](./steps/step_3.md)

- [ ] Implementation: `test_time_limit` and `test_no_time_limit_keeps_git_guard` first, then `RERUN_NOTE`, `_limit`, time check in `_report`, docstring, `tests/README.md` "Test guards" section; handle unit-group violations
- [ ] Quality checks (pylint, unit-group pytest, serial `tests/test_guards.py`, serial performance run, mypy, ruff, vulture, file size) — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against the summary and issue #417
- [ ] PR summary prepared
