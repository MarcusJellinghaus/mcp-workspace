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

### Step 1: `format_rate_limit_error` and extra diagnostic headers
See [step_1.md](./steps/step_1.md)

- [x] Implementation: tests in `test_diagnostics.py`, then `format_rate_limit_error` + `X-RateLimit-Reset/-Used/-Resource` headers in `_diagnostics.py`
- [x] Quality checks: pylint, pytest, mypy, lint-imports — fix all issues
- [x] Commit message prepared

### Step 2: Fail-fast rate-limit cap
See [step_2.md](./steps/step_2.md)

- [x] Implementation: verify `GithubRetry(max_rate_limit_wait=...)` exists; tests in `test_client.py`, then `GITHUB_MAX_RATE_LIMIT_WAIT = 60` in `_client.py` and `PyGithub>=2.10.0` in `pyproject.toml`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: Shared login cache in `base_manager`
See [step_3.md](./steps/step_3.md)

- [x] Implementation: autouse `reset_login_cache` fixture + `TestLoginCache` tests, then `_login_cache`, `_cached_login`, `clear_login_cache` in `base_manager.py`; re-exports in `__init__.py`; `_diagnostics.py` docstring
- [x] Quality checks: pylint, pytest, mypy, vulture — fix all issues
- [x] Commit message prepared

### Step 4: Rate-limit reporting and re-raise in `base_manager`
See [step_4.md](./steps/step_4.md)

- [ ] Implementation: tests in `test_base_manager.py`, then rate-limit checks in `_handle_github_errors`, `_get_repository`, `get_authenticated_username`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: Server `@me` uses the shared login cache
See [step_5.md](./steps/step_5.md)

- [ ] Implementation: update server write-tool tests (remove per-file fixtures, add `github_token`, new per-token test), then `_resolve_assignees` via `_cached_login` and remove `server._login_cache`
- [ ] Quality checks: pylint, pytest, mypy, lint-imports, vulture — fix all issues
- [ ] Commit message prepared

### Step 6: Rate-limit replies in all `github_*` server tools
See [step_6.md](./steps/step_6.md)

- [ ] Implementation: rate-limit reply tests, then `_tool_error`, `_api_error` rate-limit check, widened `RetryError` excepts, `github_issue_edit` reasons in `server.py`
- [ ] Quality checks: pylint, pytest, mypy, lint-imports — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
