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

### Step 1: `github_label_list` gains `reference_name`

Details: [step_1.md](./steps/step_1.md)

- [x] Implementation: create `tests/github_operations/test_github_write_tools_reference.py` (test-first) and add `reference_name` to `github_label_list` via `_issue_manager(reference_name)`, removing the local `IssueManager` import and updating the docstring
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `github_issue_comment` gains `reference_name`, plus the `_ref_suffix` helper

Details: [step_2.md](./steps/step_2.md)

- [x] Implementation: add the `github_issue_comment` case and failure-message tests, then add the `_ref_suffix` helper, the `reference_name` parameter, the `_issue_manager` swap and the suffixed failure sentinel
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: `github_issue_create` gains `reference_name`; `_check_labels` learns the name

Details: [step_3.md](./steps/step_3.md)

- [x] Implementation: add the `github_issue_create` case and the three message tests, then add `reference_name` to `_check_labels` and `github_issue_create`, making the `status-*` advice and unknown-label message conditional while keeping the workspace path byte-identical
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared — message is in commit `a0fc547`; `pr_info/.commit_message.txt` itself could not be written (gitignored, MCP write tools refuse it, no shell tool available)

### Step 4: `github_issue_edit` gains `reference_name`

Details: [step_4.md](./steps/step_4.md)

- [ ] Implementation: add the `github_issue_edit` case and the four tests, then add `reference_name`, swap the manager construction, pass the name to `_check_labels`, suffix the not-found sentinel, and keep the pre-write validations ahead of resolution
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: Tool enumeration, documentation, skill and local allowlist

Details: [step_5.md](./steps/step_5.md)

- [ ] Implementation: update the enumeration in `server_reference_tools.py` plus its two exact-equality assertions and the verbatim README quote, then the README/CLAUDE.md/SKILL.md prose, `.claude/settings.local.json` and the `tests/LLM_Test.md` Section 4 script
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: verify all steps implemented, checks green, and no unintended changes
- [ ] PR summary prepared
