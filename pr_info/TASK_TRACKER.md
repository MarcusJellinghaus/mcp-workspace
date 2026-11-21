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

<!-- Tasks populated from pr_info/steps/ by prepare_task_tracker -->

### Step 1: Case-insensitive pattern classes; access-rules fix — [step_1.md](./steps/step_1.md)

- [x] Implementation: tests first (win32 fixture, `[b-a]x` invalid case, parametrized win32 match test, bytes/`GlobPattern` prefix test, semantics regression), then `_CaseInsensitiveOnWin32` mixin, `AccessRulePattern`, `GlobPattern`, `_compiles` catching `re.error`, no `_fold` in `load_access_rules` / `match`, `_fold` docstring, `docs/ARCHITECTURE.md` matching line
- [x] Quality checks (format, pylint, pytest, mypy, ruff, vulture, lint-imports) — fix all issues
- [x] Commit message prepared

### Step 2: `search_files` glob fix — [step_2.md](./steps/step_2.md)

- [ ] Implementation: tests first (`[b-a]x` in glob validation, win32 fixture, `_match_glob` win32 case-insensitive and reversed-range tests), then `_match_glob` using `GlobPattern`, `_nothing_matches` helper, `re.error` → `ValueError`, remove `.lower()` / `import sys`, `docs/ARCHITECTURE.md` module line, `docs/release-notes.md` section
- [ ] Quality checks (format, pylint, pytest incl. serial performance run, mypy, ruff, vulture, lint-imports) — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main`
- [ ] Write Obsidian `Field Notes/` entry (`Promote into [[mcp-workspace]]`) on case-insensitive matching no longer lower-casing
- [ ] PR summary prepared
