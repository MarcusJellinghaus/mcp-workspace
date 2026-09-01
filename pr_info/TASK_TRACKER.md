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

### Step 1: Pin current glob semantics (tests only) — [step_1.md](./steps/step_1.md)

- [ ] Implementation: add `TestSearchFilesGlobSemantics` to `tests/file_tools/test_search.py` (trailing slash, character-class negation, `**`, POSIX case sensitivity); no production code changes
- [ ] Quality checks: pylint, pytest (`-n auto`), mypy — fix all issues
- [ ] Commit message prepared: `test(search): pin gitignore glob semantics`

### Step 2: Raise on globs that match nothing by construction — [step_2.md](./steps/step_2.md)

- [ ] Implementation: add `TestSearchFilesGlobValidation` tests, extract `_match_glob(glob, files)` in `search.py` with the single `ValueError` condition, update `search_files` `Raises:`, raise the `pathspec` floor to `>=1.1.1` in `pyproject.toml`
- [ ] Quality checks: pylint, pytest (`-n auto`), mypy, ruff — fix all issues
- [ ] Commit message prepared: `fix(search): raise on globs that match nothing by construction`

### Step 3: `glob_note` for brace globs that match no files — [step_3.md](./steps/step_3.md)

- [ ] Implementation: add `TestSearchFilesGlobNote` tests, add `_BRACE_NOTE` and `_glob_note`, attach `glob_note` to both file-search and content-search return paths; leave `note` and `_search_content`'s signature unchanged
- [ ] Quality checks: pylint, pytest (`-n auto`), mypy, ruff — fix all issues
- [ ] Commit message prepared: `feat(search): flag brace globs that match no files`

### Step 4: Document glob semantics in all three docstrings — [step_4.md](./steps/step_4.md)

- [ ] Implementation: create `tests/test_tool_descriptions.py` guard test, write the four documented behaviours plus `glob_note` and `Raises:` into the `server.search_files`, `server_reference_tools.search_reference_files`, and `file_tools.search.search_files` docstrings; add DOC502 `per-file-ignores` if ruff fires
- [ ] Quality checks: pylint, pytest (`-n auto`), mypy, ruff — fix all issues
- [ ] Commit message prepared: `docs(search): document glob semantics in tool descriptions`

## Pull Request

- [ ] PR review: verify all steps complete, checks pass, no `.scratch/` leftovers
- [ ] PR summary prepared
