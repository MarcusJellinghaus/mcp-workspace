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

### Step 1: `cli` package and section formatters — [step_1.md](./steps/step_1.md)
- [x] Implementation: `tests/cli/test_verify_formatting.py` first, then `cli/__init__.py`, `cli/verify_formatting.py`, `.importlinter` and `tach.toml` updates
- [x] Quality checks (format, ruff, pylint, mypy, pytest, lint-imports, tach, vulture) — fix all issues
- [x] Commit message prepared: `feat(cli): add verify section formatters`

### Step 2: `github_security_rows` and PyYAML — [step_2.md](./steps/step_2.md)
- [x] Implementation: `tests/github_operations/test_security_rows.py` first, then `github_operations/security_rows.py`, `__init__.py` re-export, `pyproject.toml` (PyYAML, types-PyYAML), `.importlinter` yaml contract
- [x] Quality checks (format, ruff, pylint, mypy, pytest, lint-imports, tach, deptry, vulture) — fix all issues
- [x] Commit message prepared: `feat(github_operations): add github_security_rows`

### Step 3: `execute_verify` — [step_3.md](./steps/step_3.md)
- [x] Implementation: `tests/cli/test_verify.py` first, then `cli/verify.py`
- [x] Quality checks (format, ruff, pylint, mypy, pytest, lint-imports, tach, vulture) — fix all issues
- [x] Commit message prepared: `feat(cli): add execute_verify`

### Step 4: `main.py` reference validation split and `verify` dispatch — [step_4.md](./steps/step_4.md)
- [x] Implementation: extend `tests/test_main_validate_reference_projects.py` and create `tests/test_main_verify.py` first, then `main.py` changes
- [x] Quality checks (format, ruff, pylint, mypy, pytest parallel + serial performance run, lint-imports, tach, vulture) — fix all issues
- [x] Commit message prepared: `feat(main): add mcp-workspace verify subcommand`

### Step 5: Documentation — [step_5.md](./steps/step_5.md)
- [x] Implementation: `docs/verify.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/file-access.md`, `docs/release-notes.md`
- [x] Quality checks (check_file_size README ≤ 750 lines, pytest) — fix all issues
- [x] Commit message prepared: `docs: document mcp-workspace verify`

## Pull Request
- [x] Full test suite after rebase onto `main`, run per group as in [summary.md — Running the test suite](./steps/summary.md#running-the-test-suite-timing-see-416--417) — all groups pass, pylint and mypy clean
- [ ] PR review: review the full branch diff against `main`
- [ ] PR summary prepared
