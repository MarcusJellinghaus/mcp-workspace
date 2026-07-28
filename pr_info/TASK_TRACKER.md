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

### Step 1: Rewrite the 7 docstring summary lines

Detail: [step_1.md](./steps/step_1.md)

- [x] Implementation: rewrite the first docstring line of `read_file`, `save_file`, `delete_directory`, `move_file`, `edit_file`, `git` (`server.py`) and `read_reference_file` (`server_reference_tools.py`); grep tests confirm no old summary strings are pinned
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Sync the stale README feature summaries

Detail: [step_2.md](./steps/step_2.md)

> Shares a single commit with Step 1 (README bullets must be byte-identical to the Step 1 docstring first lines).

- [ ] Implementation: update the `read_file`, `save_file`, `edit_file`, and `read_reference_file` feature bullets in `README.md` to match the Step 1 summaries
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] Address PR review feedback
- [ ] Write PR summary
