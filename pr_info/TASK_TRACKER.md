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

### Step 1: Unify and harden `normalize_path`

Details: [step_1.md](./steps/step_1.md)

- [x] Implementation: `requires_symlinks` marker in `tests/conftest.py`, 2 fixtures + 4 parametrized tests in `tests/file_tools/test_path_utils.py`, rewritten `normalize_path` + `_outside_error` in `src/mcp_workspace/file_tools/path_utils.py`, `import os` removed
- [x] Quality checks: pylint, pytest, mypy (plus ruff and vulture) — fix all issues
- [x] Commit message prepared: `fix(path_utils): validate absolute paths against the resolved path (#290)`

### Step 2: `search_files` skips a rejected file and reports it

Details: [step_2.md](./steps/step_2.md)

- [x] Implementation: 3 tests in `tests/file_tools/test_search.py`, `_search_content` skip/report with `skipped_files` in `src/mcp_workspace/file_tools/search.py`, docstring line in `server.py` and `server_reference_tools.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared: `fix(search): skip and report files rejected by the path guard (#290)`

### Step 3: Operation-level absolute-traversal coverage

Details: [step_3.md](./steps/step_3.md)

- [x] Implementation: one parametrized test over the seven operations in `tests/file_tools/test_file_operations.py` (test-only; no source change)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared: `test(file_operations): cover absolute-path traversal (#290)`

### Step 4: Reference-project traversal coverage

Details: [step_4.md](./steps/step_4.md)

- [x] Implementation: one async `read_reference_file` traversal test in `tests/test_reference_projects_mcp_tools.py` (test-only; no source change)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared: `test(reference): cover absolute-path traversal (#290)`

### Step 5: Document the newly rejected input classes in README.md

Details: [step_5.md](./steps/step_5.md)

- [ ] Implementation: `## Path Confinement` section after `## Overview` plus one cross-reference bullet in the reference-project Security Notes list (docs-only)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared: `docs(readme): state the two paths the guard now rejects (#290)`

## Pull Request

- [ ] PR review: verify the full diff against [summary.md](./steps/summary.md), including the "Traps to carry through every step" list and the tests that must pass unchanged
- [ ] PR summary: describe the fix, both breaking changes, and state that variant 2 (symlink escape) is verified only by the Ubuntu CI job
