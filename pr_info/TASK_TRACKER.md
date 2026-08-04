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

### Step 1: Make `_handle_github_errors` call callable defaults

See [step_1.md](./steps/step_1.md).

- [x] Implementation: add `callable(default_return)` guard at both return sites in `_handle_github_errors` (`base_manager.py`); add the three tests to `TestHandleGitHubErrorsDecorator` (`test_base_manager.py`); update decorator docstring
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Add `MergeResult`, `_failed_merge_result()`, `merge_pull_request()`

See [step_2.md](./steps/step_2.md).

- [x] Implementation: add `MergeResult`, `_failed_merge_result()`, and `merge_pull_request()` to `pr_manager.py`; create `test_pr_manager_merge.py` covering every acceptance case
- [x] Quality checks: pylint, pytest (fast-unit + git_integration marker), mypy — fix all issues
- [x] Commit message prepared (message is on commit 25d44ad; the `pr_info/.commit_message.txt` scratch file is gitignored and cannot be written via MCP `save_file`)

### Step 3: Export `MergeResult` and `PullRequestData`

See [step_3.md](./steps/step_3.md).

- [ ] Implementation: import and add `MergeResult` + `PullRequestData` to `__all__` in `github_operations/__init__.py`; add importability test
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: verify all steps complete, checks pass, and changes match the summary
- [ ] PR summary prepared
