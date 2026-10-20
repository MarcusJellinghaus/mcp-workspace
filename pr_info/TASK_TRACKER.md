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

<!-- Tasks populated from pr_info/steps/ by prepare_task_tracker -->

### Step 1: `on_error` parameter on `_handle_github_errors`
See [step_1.md](./steps/step_1.md)

- [x] Implementation: tests in `test_base_manager.py` + optional `on_error` parameter in `base_manager.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `_last_repository_error` on `BaseGitHubManager`
See [step_2.md](./steps/step_2.md)

- [x] Implementation: tests in `test_base_manager.py` + `_format_error_message` helper and `_last_repository_error` set in `_get_repository()`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: Wire `lookup_error` into `CIStatusData` / `get_latest_ci_status`
See [step_3.md](./steps/step_3.md)

- [x] Implementation: tests in `test_ci_results_manager_status.py` + `lookup_error` field, `_set_lookup_error` helper, decorator `on_error` wiring, and repo-inaccessible branch in `ci_results_manager.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

## Pull Request

- [ ] PR review: review full branch diff against `main`
- [ ] PR summary prepared
