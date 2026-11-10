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

### Step 1: Pin the MCP tool schemas in a snapshot
See [step_1.md](./steps/step_1.md)
- [x] Implementation: snapshot test + `tool_schema_snapshot.json` captured from current server
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [x] Commit message prepared

### Step 2: `toolset` skeleton, `create_server`, `FastMCPSink`, test fixtures
See [step_2.md](./steps/step_2.md)
- [x] Implementation: `tool_specs`/`WorkspaceContext`, `create_server` + `FastMCPSink`, `_legacy_tool`/`_configure_legacy`, `make_tools`/`tools` fixtures, contracts (tests + production code)
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [x] Commit message prepared

### Step 3: Move group `workspace.read` (`read_file`, `list_directory`, `search_files`)
See [step_3.md](./steps/step_3.md)
- [x] Implementation: `toolset/read.py`, remove unused legacy code, migrate tests
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [x] Commit message prepared

### Step 4: Move group `workspace.write` (`save_file`, `edit_file`, `append_file`)
See [step_4.md](./steps/step_4.md)
- [x] Implementation: `toolset/write.py`, remove unused legacy code, migrate tests
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [x] Commit message prepared

### Step 5: Move group `workspace.delete` (`delete_this_file`, `delete_directory`)
See [step_5.md](./steps/step_5.md)
- [x] Implementation: `toolset/delete.py`, remove unused legacy code, migrate tests
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [x] Commit message prepared

### Step 6: Move group `workspace.move` (`move_file`)
See [step_6.md](./steps/step_6.md)
- [x] Implementation: `toolset/move.py`, remove unused legacy code, migrate tests
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [x] Commit message prepared

### Step 7: Move group `workspace.reference` (4 reference tools)
See [step_7.md](./steps/step_7.md)
- [x] Implementation: `toolset/reference.py`, remove unused legacy code, migrate tests
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [x] Commit message prepared

### Step 8: Move group `workspace.git` (`git`)
See [step_8.md](./steps/step_8.md)
- [x] Implementation: `toolset/git.py`, remove unused legacy code, migrate tests
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [x] Commit message prepared

### Step 9: Move `workspace.github` read tools + `_github_common.py`
See [step_9.md](./steps/step_9.md)
- [ ] Implementation: `toolset/_github_common.py`, `toolset/github_read.py`, remove unused legacy code, migrate tests
- [ ] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [ ] Commit message prepared

### Step 10: Move `workspace.github` write tools; delete `server_reference_tools.py`
See [step_10.md](./steps/step_10.md)
- [ ] Implementation: `toolset/github_write.py`, delete `server_reference_tools.py` and its setter tests, migrate tests
- [ ] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [ ] Commit message prepared

### Step 11: Move group `workspace.checks`; remove the legacy machinery
See [step_11.md](./steps/step_11.md)
- [ ] Implementation: `toolset/checks.py`, remove `_legacy_tool`/`_configure_legacy`/`_project_dir`/`set_project_dir`, migrate tests
- [ ] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [ ] Commit message prepared

### Step 12: Acceptance tests for the exported toolset
See [step_12.md](./steps/step_12.md)
- [ ] Implementation: `tests/toolset/test_toolset.py` (groups, isolation, defaults, `args_model`)
- [ ] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [ ] Commit message prepared

### Step 13: Subprocess import tests — no `mcp`, lazy git/GitHub
See [step_13.md](./steps/step_13.md)
- [ ] Implementation: `tests/toolset/test_toolset_imports.py`
- [ ] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [ ] Commit message prepared

### Step 14: Documentation
See [step_14.md](./steps/step_14.md)
- [ ] Implementation: README, ARCHITECTURE, CONTRIBUTING, tests/README, release notes
- [ ] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry) — fix all issues
- [ ] Commit message prepared

## Pull Request
- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared (title + description)
