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

### Step 1: Shared normalisation and counting from `mcp_coder_utils.fs` — [step_1.md](./steps/step_1.md)

- [ ] Implementation: tach entry for `mcp_coder_utils.fs`; `normalize_line_endings` / `count_line_endings` imported from `fs`; `_normalize_newlines` delegates; duplicate tests deleted; ARCHITECTURE.md Shared Libs row
- [ ] Quality checks (pylint, pytest, mypy, ruff, tach, lint-imports, vulture) — fix all issues
- [ ] Commit message prepared

### Step 2: `edit_file` / `append_file` write via `fs.write_text` — [step_2.md](./steps/step_2.md)

- [ ] Implementation: lone-surrogate tests first; `_write_file` deleted, `edit_file` and `append_file` write via `write_text`
- [ ] Quality checks (pylint, pytest, mypy, ruff, tach, lint-imports, vulture) — fix all issues
- [ ] Commit message prepared

### Step 3: LF default via `fs.dominant_newline`; remove `PLATFORM_NEWLINE` — [step_3.md](./steps/step_3.md)

- [ ] Implementation: test reworks first (LF fallback, no platform patch); `target_newline` via `dominant_newline`, LF fallback; docstrings, tool descriptions, release notes
- [ ] Quality checks (pylint, pytest, mypy, ruff, tach, lint-imports, vulture; no `PLATFORM_NEWLINE` / `platform default` in `src/` or `tests/`) — fix all issues
- [ ] Commit message prepared

### Step 4: Path containment via `fs.check_path_within` — [step_4.md](./steps/step_4.md)

- [ ] Implementation: `normalize_path` wraps `check_path_within`; docstrings; test rename; file-access.md, ARCHITECTURE.md §6, release notes
- [ ] Quality checks (pylint, pytest, mypy, ruff, tach, lint-imports, vulture) — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main`; address findings
- [ ] PR summary prepared (intended behaviour change and accepted side effects from [summary.md](./steps/summary.md))
