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

### Step 1: Cap the violation and stale-entry lists at 50 — [step_1.md](./steps/step_1.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared: `feat(file_sizes): cap violation and stale-entry reports at 50`

### Step 2: State `check_file_size`'s scan scope in its docstring — [step_2.md](./steps/step_2.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared: `docs(server): state check_file_size scan scope`

### Step 3: README — correct List Directory's `.gitignore` claim, add a `check_file_size` entry — [step_3.md](./steps/step_3.md)

Runs after step 1 — documents the caps step 1 introduces.

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared: `docs(readme): document check_file_size and fix gitignore scope`

### Step 4: Correct the file-size check scope in `refactoring-guide.md` — [step_4.md](./steps/step_4.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared: `docs(refactoring-guide): correct file-size check scope`

## Pull Request

- [x] PR review
- [ ] PR summary
