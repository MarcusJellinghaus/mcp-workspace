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

### Step 1: `formatters.truncate_output` — name the cap and `max_lines`

Details: [step_1.md](./steps/step_1.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `output_filtering.truncate_output` — restyle to the house pattern

Details: [step_2.md](./steps/step_2.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 3: `ci_log_parser` — one marker, one spelling, name `max_log_lines`

Details: [step_3.md](./steps/step_3.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 4: `github_issue_list` — make the silent truncation notice reachable

Details: [step_4.md](./steps/step_4.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: `github_search` — emit a notice with the exact total from `totalCount`

Details: [step_5.md](./steps/step_5.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 6: `pr_feedback` — reorder sections, restyle notices, add a conditional footer

Details: [step_6.md](./steps/step_6.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 7: `tree_listing` — name the narrowing options in the truncation summary

Details: [step_7.md](./steps/step_7.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 8: `file_tools` internal caps — state the cap in `search.py`, document both

Details: [step_8.md](./steps/step_8.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review
- [ ] PR summary
