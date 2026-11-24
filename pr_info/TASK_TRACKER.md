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

### Step 1: `auto_delete_branches` reports "not accessible" when unreadable — [step_1.md](./steps/step_1.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy) — fix all issues
- [ ] Commit message prepared

### Step 2: Check-lookup 403/401 texts and skill row — [step_2.md](./steps/step_2.md)

- [ ] Implementation (tests + production code + skill row)
- [ ] Quality checks (pylint, pytest, mypy, ruff) — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review — all steps implemented, all checks pass
- [ ] PR summary prepared
