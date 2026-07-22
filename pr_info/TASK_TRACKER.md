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

### Step 1: Relocate the six healthy test files into `issues/`

Detail: [step_1.md](./steps/step_1.md)

- [x] Implementation: `move_file` the six healthy test files into `tests/github_operations/issues/` with the exact renames (no content changes)
- [x] Quality checks: pylint, pytest (incl. git markers + repo-wide `--collect-only`), mypy — fix all issues
- [x] Commit message prepared

### Step 2: Create `test_types.py` (`create_empty_issue_data`)

Detail: [step_2.md](./steps/step_2.md)

- [x] Implementation: create `tests/github_operations/issues/test_types.py` with focused unit tests for `create_empty_issue_data`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: Create `test_base.py` (move `validate_*` + NEW `parse_base_branch`)

Detail: [step_3.md](./steps/step_3.md)

- [x] Implementation: create `test_base.py` (move the two `validate_*` tests verbatim + add new `parse_base_branch` tests); remove them from the core file
- [x] Quality checks: pylint, pytest (new file + core file with git markers), mypy — fix all issues
- [x] Commit message prepared (BLOCKED: pr_info/.commit_message.txt is gitignored; MCP file tools refuse it and Bash is disabled — message text provided in run output)

### Step 4: Create `test_manager.py` (rename core + fold `test_list_issues.py`)

Detail: [step_4.md](./steps/step_4.md)

- [x] Implementation: `move_file` core to `issues/test_manager.py`, fold in `TestListIssuesExtendedParams`, delete `test_list_issues.py`
- [x] Quality checks: pylint, pytest (incl. git markers + `--collect-only`), mypy, `check_file_size(750)` — fix all issues
- [x] Commit message prepared

### Step 5: Split `test_issue_cache.py` → `test_cache_*.py` + drop allowlist line

Detail: [step_5.md](./steps/step_5.md)

- [x] Implementation: split into 4–5 `test_cache_*.py` files by whole class (keep `_make_cursor_issue` with its users), delete original, remove its `.large-files-allowlist` line
- [x] Quality checks: pylint, pytest (incl. git markers), mypy, `check_file_size(750)` — fix all issues
- [x] Commit message prepared

### Step 6: Split branch-manager tests → `test_branch_manager_*.py` (fold 3) + drop 2 allowlist lines

Detail: [step_6.md](./steps/step_6.md)

- [x] Implementation: split/fold four source files into 4–5 `test_branch_manager_*.py` files by whole class (only `TestGetBranchWithPRFallback` divided), delete sources, remove the two allowlist lines
- [x] Quality checks: pylint, pytest (incl. git markers + `--collect-only`), mypy, tach, lint-imports, `check_file_size(750)` — fix all issues
- [x] Commit message prepared (BLOCKED: pr_info/.commit_message.txt is gitignored; MCP file tools refuse it and Bash is disabled — message text provided in run output)

## Pull Request

- [ ] Address PR review feedback
- [ ] Write PR summary
