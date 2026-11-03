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

### Step 1: Move `_chunk_paths` to `core.py`
See [step_1.md](./steps/step_1.md)

- [ ] Implementation: update test import, move `_chunk_paths` from `staging.py` to `core.py`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 2: Add `renormalize_paths`
See [step_2.md](./steps/step_2.md)

- [ ] Implementation: `crlf_repo` fixture, tests, `renormalize_paths` in `staging.py`, export + export tests, release notes
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 3: Add `is_staged_diff_cr_only`
See [step_3.md](./steps/step_3.md)

- [ ] Implementation: tests, `is_staged_diff_cr_only` in `repository_status.py`, export + export tests, release notes
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
