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

### Step 1: Types, manager method, re-exports, author short-circuit, repository/number order
See [step_1.md](./steps/step_1.md)

- [x] Implementation: tests in `test_body_trust.py` + `body_trust.py` (decision steps 1–4), `IssueManager.check_body_trust`, re-exports
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Editor response parsing and editor / allowlist / token decisions
See [step_2.md](./steps/step_2.md)

- [x] Implementation: tests + `_LookupFailed`, `_editor_login`, decision steps 5–7 (replace Step 1 placeholder)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: Exception mapping on the editor and token-user paths
See [step_3.md](./steps/step_3.md)

- [x] Implementation: tests + `_call`, route GraphQL query and token-user lookup through it
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: Docs — README "Commenter trust" and release notes
See [step_4.md](./steps/step_4.md)

- [x] Implementation: update README `trusted_commenters` bullet, add "Body trust" bullet, add release-notes `### New API` bullets
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

## Pull Request

- [ ] PR review: review full branch diff against `main`
- [ ] PR summary prepared
