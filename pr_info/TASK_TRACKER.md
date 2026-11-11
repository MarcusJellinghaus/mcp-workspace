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

### Step 1: `get_eol_attribute` in `git_operations` — [step_1.md](./steps/step_1.md)

- [x] Implementation: tests (`test_eol_attribute.py`, export count 70 → 71) + `get_eol_attribute` in `file_tracking.py`, exported from `__init__.py`
- [x] Quality checks (pylint, pytest `-n auto`, mypy, lint-imports, format) — fix all issues
- [x] Commit message prepared

### Step 2: `file_tools/line_endings.py` — [step_2.md](./steps/step_2.md)

- [x] Implementation: tests (`test_line_endings.py`) + `PLATFORM_NEWLINE`, `count_line_endings`, `describe_line_endings`, `target_newline`, `_eol_from_gitattributes`
- [x] Quality checks (pylint, pytest `-n auto`, mypy, lint-imports, format) — fix all issues
- [x] Commit message prepared

### Step 3: `edit_file` keeps line endings — [step_3.md](./steps/step_3.md)

- [x] Implementation: rewrite `test_crlf_normalization`, new tests in `test_line_endings_file_tools.py` + byte read and `newline=` write in `edit_file.py`, tool docstring in `toolset/write.py`
- [x] Quality checks (pylint, pytest `-n auto`, mypy, format) — fix all issues
- [x] Commit message prepared

### Step 4: `save_file` keeps line endings — [step_4.md](./steps/step_4.md)

- [x] Implementation: rewrite `test_save_file_normalizes_crlf`, new tests in `test_line_endings_file_tools.py` + `save_file` / `_write_file_atomically` newline handling, tool docstring
- [x] Quality checks (pylint, pytest `-n auto`, mypy, format) — fix all issues
- [x] Commit message prepared

### Step 5: `append_file` becomes a real append in the file's ending — [step_5.md](./steps/step_5.md)

- [x] Implementation: rewrite `test_append_file_normalizes_crlf`, new tests in `test_line_endings_file_tools.py` + `"a"`-mode append with `target_newline`, tool docstring
- [x] Quality checks (pylint, pytest `-n auto`, mypy, format) — fix all issues
- [x] Commit message prepared

### Step 6: `format_issue_view(body_note=…)` — [step_6.md](./steps/step_6.md)

- [x] Implementation: tests (`test_formatters_body_note.py`) + keyword-only `body_note` in `formatters.py`
- [x] Quality checks (pylint, pytest `-n auto`, mypy, format) — fix all issues
- [x] Commit message prepared

### Step 7: `check_body_target` / `save_body` helpers — [step_7.md](./steps/step_7.md)

- [x] Implementation: tests (`test_github_issue_view_body_file.py`) + `check_body_target` and `save_body` in `_github_write_helpers.py`
- [x] Quality checks (pylint, pytest `-n auto`, mypy, format) — fix all issues
- [x] Commit message prepared

### Step 8: `github_issue_view(body_file=…)` with round-trip tests — [step_8.md](./steps/step_8.md)

- [ ] Implementation: tool-level and round-trip tests + `body_file` parameter and docstring in `github_read.py`
- [ ] Quality checks (pylint, pytest `-n auto`, mypy, format) — fix all issues
- [ ] Commit message prepared

### Step 9: Docs — README, `LIBRARY_USE.md`, `LLM_Test.md` — [step_9.md](./steps/step_9.md)

- [ ] Implementation: README (existing lines only, ≤ 750), `docs/LIBRARY_USE.md` `read_only` exception, `tests/LLM_Test.md` Test 4.1b round trip
- [ ] Quality checks (`check_file_size`, pytest `-n auto`) — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main`; address findings
- [ ] PR summary prepared
