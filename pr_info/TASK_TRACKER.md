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

### Step 1: Label disk cache — `new_expiry(max_age)` + `caching/labels.py`
See [step_1.md](./steps/step_1.md)

- [x] Implementation: tests in `test_store.py` / new `test_labels.py`, then `new_expiry(now, max_age)` and `get_cached_labels` with `_valid_entry` and footers
- [x] Quality checks: pylint, pytest, mypy (plus lint-imports) — fix all issues
- [x] Commit message prepared

### Step 2: `github_label_list` reads through the label cache
See [step_2.md](./steps/step_2.md)

- [x] Implementation: move autouse `cache_dir` fixture up to `tests/github_operations/conftest.py`, fix manager mocks and `test_get_cache_file_path_basic`; add `_rate_limit_message`, update `_tool_error`/`_api_error`, add `refresh_labels` + footer to `github_label_list`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: `LabelsMixin.get_issue_for_status`
See [step_3.md](./steps/step_3.md)

- [x] Implementation: tests in `test_labels_mixin.py`, then `get_issue_for_status` (no `_handle_github_errors`, PR rejection, repo-unavailable `ValueError`)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: `set_issue_labels_in_cache` (coordinator issue cache)
See [step_4.md](./steps/step_4.md)

- [x] Implementation: tests in `test_cache_update.py`, then `set_issue_labels_in_cache` in `issues/cache.py` (debug on miss, warning on failure, never raises)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 5: `issues/status.py` — `set_issue_status`
See [step_5.md](./steps/step_5.md)

- [ ] Implementation: new `test_status.py`, then `STATUS_LABEL_PREFIX`, `is_status_label`, `set_issue_status` with exact result texts
- [ ] Quality checks: pylint, pytest, mypy (plus lint-imports) — fix all issues
- [ ] Commit message prepared

### Step 6: `github_issue_set_status` MCP tool + `_check_labels` wording
See [step_6.md](./steps/step_6.md)

- [ ] Implementation: new `test_github_issue_set_status.py`, reference `_TOOL_CASES`/`_TOOL_IDS`, updated `set-status` assertions; add the tool, switch `_check_labels` to `is_status_label`, delete `_STATUS_LABEL_PREFIX`, update create/edit docstrings, vulture whitelist
- [ ] Quality checks: pylint, pytest, mypy (plus vulture) — fix all issues
- [ ] Commit message prepared

### Step 7: Docs and `.claude/` config
See [step_7.md](./steps/step_7.md)

- [ ] Implementation: update `SECURITY.md`, `README.md`, `tests/LLM_Test.md`, `.claude/CLAUDE.md`, `.claude/settings.local.json`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main`, address findings
- [ ] PR summary prepared (mention that the `.claude/` changes must be synced back to mcp-coder after merge, before the next Shared Config Sync)
