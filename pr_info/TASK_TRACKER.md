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

### Step 1: Extract `_pr_to_data`, add `assignees` field, update `create_mock_pr`

See [step_1.md](./steps/step_1.md).

- [x] Implementation: add `assignees` field + `_pr_to_data` helper, route the 5 serialization sites, remove redundant inner `try/except`, update `create_pull_request` docstring, and add `create_mock_pr` `assignees=[]` default with cross-method assertions
- [x] Quality checks: pylint, pytest (`-n auto`, marker `git_integration`), mypy — fix all issues
- [x] Commit message prepared (blocked: pr_info/.commit_message.txt is gitignored and MCP file tools refuse gitignored paths; no Bash tool available — message text provided in run output)

### Step 2: Add `PullRequestManager.add_assignees()` + tests

See [step_2.md](./steps/step_2.md).

- [ ] Implementation: add `add_assignees(self, pr_number, *logins)` method and create `tests/github_operations/test_pr_manager_add_assignees.py` with the five cases
- [ ] Quality checks: pylint, pytest (`-n auto`, marker `git_integration`), mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: verify all steps complete and checks pass across the branch
- [ ] PR summary prepared
