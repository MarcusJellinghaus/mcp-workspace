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

### Step 1: Extract `SearchSpec` into `github_operations/search.py`

Details: [step_1.md](./steps/step_1.md)

- [x] Implementation: write `tests/github_operations/test_search.py` first, create `src/mcp_workspace/github_operations/search.py`, rewrite the `github_search` handler body in `server.py` and drop `import re`, trim the 15 moved tests from `test_github_search_tool.py` and update its module docstring
- [x] Quality checks: pylint, pytest, mypy — plus vulture, ruff, lint-imports, tach — fix all issues
- [x] Commit message prepared: `refactor(github_search): extract SearchSpec into github_operations`

### Step 2: Exclude `TYPE_CHECKING` imports in import-linter, drop the `base_branch` waivers

Details: [step_2.md](./steps/step_2.md)

- [x] Implementation: add `exclude_type_checking_imports = True` with the trade-off comment to the `[importlinter]` block and delete the `ignore_imports` key with both `base_branch` entries from the layered contract — both edits in one commit
- [x] Quality checks: pylint, pytest, mypy — plus lint-imports and tach — fix all issues
- [x] Commit message prepared: `chore(importlinter): exclude TYPE_CHECKING imports, drop base_branch waivers`

## Pull Request

- [ ] PR review: verify the refactor is behaviour-preserving — query strings and error messages byte-identical, validation still ahead of `_issue_manager`, lazy import intact
- [ ] PR summary prepared
