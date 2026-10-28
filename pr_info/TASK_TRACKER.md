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

### Step 1: `_resolve_body` helper + `github_issue_create(body_file=...)` — [step_1.md](./steps/step_1.md)

- [x] Implementation: tests in new `test_github_write_tools_body_file.py`, then `_resolve_body` and `body_file` on `github_issue_create`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `github_issue_edit(body_file=...)` — [step_2.md](./steps/step_2.md)

- [x] Implementation: append edit tests, then `body_file` on `github_issue_edit` (conflict on any `body`, including `""`)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: `github_issue_comment(body_file=...)` — [step_3.md](./steps/step_3.md)

- [x] Implementation: append comment tests, then optional `body`, `body_file`, and the "pass body or body_file" guard on `github_issue_comment`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: `github_pr_create(body_file=...)` — [step_4.md](./steps/step_4.md)

- [x] Implementation: append PR create tests, then `body_file` on `github_pr_create`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 5: Approximate sub-issue count — [step_5.md](./steps/step_5.md)

- [x] Implementation: update sub-issue test assertions, then `(~N sub-issues, may lag)` in `_subissue_write` and docstrings
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 6: `check_file_size(show_allowlisted=True)` — [step_6.md](./steps/step_6.md)

- [x] Implementation: tests for `render_allowlisted` and flag routing, then `render_allowlisted`, `check_file_size` flag, cap comments
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 7: README and `tests/LLM_Test.md` — [step_7.md](./steps/step_7.md)

- [ ] Implementation: README tool table and `tests/LLM_Test.md` updates (docs only)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
