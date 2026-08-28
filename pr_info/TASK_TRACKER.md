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

### Step 1: `IssueIdentityMismatchError` + `_get_issue_checked` + export

Details: [step_1.md](./steps/step_1.md)

- [ ] Implementation: add `IssueIdentityMismatchError` and `BaseGitHubManager._get_issue_checked()` in `github_operations/base_manager.py`, export from `github_operations/__init__.py`; tests first in `tests/github_operations/test_base_manager.py` (`TestGetIssueChecked`, 4 cases) and `test_package_exports.py`. No call sites routed.
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 2: Prepare test fixtures for the guard

Details: [step_2.md](./steps/step_2.md)

- [ ] Implementation (tests only, no `src/` changes): create `tests/github_operations/_issue_test_helpers.py` with `make_mock_issue()`; set `full_name` on mocked repos in `conftest.py`, the 11 local `mock_repo`s in `test_branch_manager_create.py` and `_setup_mocks` in `test_pr_manager_feedback.py` (with `make_mock_issue(42)`); convert mock-issue sites in `test_manager.py`, `test_labels_mixin.py`, `test_comments_mixin.py`, `test_events_mixin.py`, `test_branch_manager_create.py`.
- [ ] Quality checks: pylint, pytest (fast exclusions **and** `markers=["git_integration"]`), mypy — fix all issues
- [ ] Commit message prepared

### Step 3: Route all 18 call sites through `_get_issue_checked`

Details: [step_3.md](./steps/step_3.md)

- [ ] Implementation: write the 4 new tests first (read path in `test_manager.py`, write path in `test_labels_mixin.py`, inherited path in `test_pr_manager_feedback.py`, rendered message in `test_github_read_tools.py`), then route the 18 sites in `issues/manager.py`, `issues/comments_mixin.py`, `issues/labels_mixin.py`, `issues/events_mixin.py`, `issues/branch_manager.py`, `_pr_feedback_sources.py`; update `Raises:`/`Returns:` docstrings on the routed public methods plus `transition_issue_label`. Leave `server.py:717` unrouted; verify `repo.get_issue(` matches exactly one line in `src/`.
- [ ] Quality checks: pylint, pytest (fast exclusions **and** `markers=["git_integration"]`), mypy, lint-imports — fix all issues
- [ ] Commit message prepared

### Step 4: Visible warning in `check_branch_status`

Details: [step_4.md](./steps/step_4.md)

- [ ] Implementation: write `test_transferred_issue_logs_warning` in `tests/checks/test_branch_status.py` first, then import `IssueIdentityMismatchError` in `checks/branch_status.py` and add the `except IssueIdentityMismatchError as e: logger.warning("%s", e)` clause before the existing broad catch (~line 510). Do not touch `git_operations/base_branch.py` or `issues/cache.py`.
- [ ] Quality checks: pylint, pytest, mypy, lint-imports — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: verify all steps complete, checks green, and no bare `repo.get_issue(` remains in the issue modules
- [ ] PR summary prepared, including the follow-up note to file an issue on **mcp_coder** (catch `IssueIdentityMismatchError` in `execute_set_status`, print the message, exit `3`)
