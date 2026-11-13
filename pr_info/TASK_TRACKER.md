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

### Step 1: Rules file parser (`access_rules.py`) — [step_1.md](./steps/step_1.md)
- [x] Implementation (pathspec probe, tests, `access_rules.py`)
- [x] Quality checks (pylint, pytest, mypy) — fix all issues
- [x] Commit message prepared

### Step 2: Effective access and public API — [step_2.md](./steps/step_2.md)
- [x] Implementation (tests, `FileAccess` / `_access` / `get_file_access` / `require_access`, exports)
- [x] Quality checks (pylint, pytest, mypy) — fix all issues
- [x] Commit message prepared

### Step 3: Single-path enforcement in the tools — [step_3.md](./steps/step_3.md)
- [x] Implementation (tests, `check_readable` / `check_writable` replace `check_not_gitignored` at all call sites)
- [x] Quality checks (pylint, pytest, mypy) — fix all issues
- [x] Commit message prepared

### Step 4: Tree checks for `move_file` / `delete_directory`; plain move into a gitignored destination — [step_4.md](./steps/step_4.md)
- [x] Implementation (tests, `check_tree_access`, `_determine_move_method(dest_ignored)`, tool call sites)
- [x] Quality checks (pylint, pytest, mypy) — fix all issues
- [x] Commit message prepared

### Step 5: Exposure-aware listing walk for `search_files` and reference listing / search — [step_5.md](./steps/step_5.md)
- [x] Implementation (tests, `list_accessible_files`, `search_files`, `list_reference_directory`)
- [x] Quality checks (pylint, pytest, mypy, serial performance tests) — fix all issues
- [x] Commit message prepared

### Step 6: `list_directory` — exposed paths, suffixes, warning line, hidden directory — [step_6.md](./steps/step_6.md)
- [x] Implementation (tests, `list_directory` switched to `list_accessible_files`)
- [x] Quality checks (pylint, pytest, mypy) — fix all issues
- [x] Commit message prepared

### Step 7: Docs — [step_7.md](./steps/step_7.md)
- [ ] Implementation (`README.md`, `SECURITY.md`, `docs/ARCHITECTURE.md`, `docs/release-notes.md`)
- [ ] Quality checks (pylint, pytest, mypy) — fix all issues
- [ ] Commit message prepared

### Step 8: `.scratch/` migration in this repo — [step_8.md](./steps/step_8.md)
- [ ] Implementation (guard test, `.mcp-file-access`, `.gitignore`, ruff probe, CLAUDE.md "Scratch probes")
- [ ] Quality checks (pylint, pytest, mypy) — fix all issues
- [ ] Commit message prepared

## Pull Request
- [ ] PR review — check the full branch diff against issue #83 and `summary.md`
- [ ] PR summary prepared (incl. note that MarcusJellinghaus/mcp_coder#1414 ships together with step 8)
