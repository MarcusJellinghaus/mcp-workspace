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

### Step 1: Formatter renders the linked-branches line ([step_1.md](./steps/step_1.md))

- [ ] Implementation: tests in `TestFormatIssueView`, then `format_issue_view` keyword-only `linked_branches` / `include_linked_branches`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 2: `github_issue_view` flag and lookup helper ([step_2.md](./steps/step_2.md))

- [ ] Implementation: tests in `test_github_read_tools_issues.py` and `test_github_read_tools_reference.py`, then `_linked_branches` helper and `include_linked_branches` in `server.py`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: check the full branch diff against `main` for issues
- [ ] PR summary prepared
