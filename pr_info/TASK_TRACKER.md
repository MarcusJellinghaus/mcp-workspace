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

### Step 1: Rules builder, `info/exclude`, `is_path_gitignored`, new message — [step_1.md](./steps/step_1.md)

- [x] Implementation: precondition probe (igittigitt >=2.4.0), tests in `tests/file_tools/test_gitignore_rules.py` + `test_server.py` message assertion, then `_info_exclude_path`, `_load_rule_file`, `_rules_for`, `_matches_rules`, new `is_path_gitignored` and message, `pyproject.toml` bump
- [x] Quality checks: pylint, pytest (`-n auto`), mypy — fix all issues
- [x] Commit message prepared

### Step 2: `list_files` walk with `skip` callback; delete old helpers — [step_2.md](./steps/step_2.md)

- [x] Implementation: listing tests in `test_gitignore_rules.py`, update `test_directory_utils.py`, then `_discover_files(skip=...)`, `_gitignore_skip`, new `list_files`, delete `read_gitignore_rules` / `_link_target_ignored` / `apply_gitignore_filter` / `filter_with_gitignore`
- [x] Quality checks: pylint, pytest (`-n auto`), mypy — fix all issues
- [x] Commit message prepared

### Step 3: `list_directory` refuses ignored directories — [step_3.md](./steps/step_3.md)

- [x] Implementation: refusal tests in `tests/test_server_list_directory.py`, then `check_not_gitignored(ctx, path)` in `toolset/read.py` and docstring `Raises:`
- [x] Quality checks: pylint, pytest (`-n auto`), mypy — fix all issues
- [x] Commit message prepared

### Step 4: Conformance test against `git check-ignore` — [step_4.md](./steps/step_4.md)

- [x] Implementation: precondition probe (git binary), `tests/file_tools/test_gitignore_conformance.py` with scenarios 01–25, worktree and submodule `info/exclude` tests; small local fix in `directory_utils.py` only if a scenario requires it
- [x] Quality checks: pylint, pytest (`-n auto`), mypy — fix all issues
- [x] Commit message prepared

### Step 5: Documentation and release notes — [step_5.md](./steps/step_5.md)

- [ ] Implementation: `README.md`, `SECURITY.md`, `docs/ARCHITECTURE.md`, `docs/processes-prompts/refactoring-guide.md`, `check_file_size` description in `toolset/checks.py`, `docs/release-notes.md`; leftover search
- [ ] Quality checks: pylint, pytest (`-n auto`), mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main`, resolve findings
- [ ] PR summary prepared (include hand-measured before/after listing timing and single-path check timing)
