# Summary — Reduce and survive GitHub REST quota exhaustion (#329)

## Goal

1. Cache the authenticated login (`GET /user`) once per `(API host, token)`, shared by
   `get_authenticated_username()` and the server's `@me` assignee resolution.
2. Fail fast on rate limits: cap `GithubRetry` waits at 60s instead of sleeping up to an hour.
3. Report rate limits as rate limits (bucket + reset time) in logs, in the
   `get_authenticated_username` `ValueError`, and in every `github_*` MCP tool reply —
   not as "Failed to authenticate" / "Could not access repository".
4. Re-raise rate limits (403 rate limit, 429, `requests.exceptions.RetryError`) from
   `_get_repository` and `_handle_github_errors` instead of swallowing them.
5. Log `X-RateLimit-Reset`, `-Used`, `-Resource` in DEBUG failure diagnostics.

The issue (#329) is the source of truth for requirements, constraints and decisions.

## Architectural / design changes

| Area | Before | After |
|---|---|---|
| Login lookup | `get_authenticated_username` calls `GET /user` every time; `server._login_cache` keyed by host only, separate | One module-level cache in `base_manager`, key `(api_base_url, sha256(token))`, private helper `_cached_login(token, base_url, client=None)`; `server._login_cache` removed; public `clear_login_cache()` for tests |
| Retry policy | `GithubRetry(total=2)`; primary rate limit sleeps until reset (≤1h) | `GithubRetry(total=2, max_rate_limit_wait=60)`; longer waits raise `RateLimitExceededExceedsMaxWait` immediately |
| Rate-limit recognition | None; 403 rate limit reads as auth error, 429 / `RetryError` swallowed as generic errors | One pure function `_diagnostics.format_rate_limit_error(exc) -> str \| None`, used by all reporting sites |
| `_get_repository` | Every failure → log + `None` | Rate limits → log + re-raise; everything else unchanged |
| `_handle_github_errors` | 401/403 re-raised, rest → default | Rate limits (incl. 429, `RetryError`) checked first → log + re-raise; rest unchanged |
| Server replies | `f"Error: {e}"` / `_api_error` | `_tool_error(e)` = `format_rate_limit_error(e) or f"Error: {e}"` in all `github_*` tools; `_api_error` checks rate limit first; three narrow `except` blocks also catch `RetryError` |
| Public API of `github_operations` | — | Adds `clear_login_cache`, `format_rate_limit_error`, `RetryError` (re-exports) |

Design notes (KISS):

- **No new exception type.** Rate-limit detection is a single pure function returning a
  message or `None`; each site does `if msg is not None: log; raise`, inline, without
  restructuring the existing `except` branches.
- **`RetryError` reaches `server.py` through a re-export** from `github_operations/__init__.py`
  (`from ._diagnostics import RetryError, format_rate_limit_error`), mirroring the existing
  `GithubException` re-export. `server.py` must never import `requests` directly — the
  "Requests Library Isolation" import-linter contract forbids it (lazy imports included).
- **No lock, no failure caching:** the helper stores only after `get_user().login` succeeds.
- Fixed 60s cap constant, not configurable.

## Files

Created:

- `pr_info/steps/summary.md`, `pr_info/steps/step_1.md` … `step_6.md` (this plan)

Modified (source):

- `src/mcp_workspace/github_operations/_diagnostics.py` — headers, `format_rate_limit_error`, `RetryError` import
- `src/mcp_workspace/github_operations/_client.py` — `GITHUB_MAX_RATE_LIMIT_WAIT`, docstring
- `src/mcp_workspace/github_operations/base_manager.py` — login cache, `clear_login_cache`, rate-limit re-raise/messages
- `src/mcp_workspace/github_operations/__init__.py` — re-exports
- `src/mcp_workspace/server.py` — `_resolve_assignees`, `_login_cache` removal, `_tool_error`, `_api_error`, widened excepts
- `pyproject.toml` — `PyGithub>=2.10.0`

Modified (tests):

- `tests/github_operations/conftest.py` — autouse `reset_login_cache`
- `tests/github_operations/test_diagnostics.py`
- `tests/github_operations/test_client.py`
- `tests/github_operations/test_base_manager.py`
- `tests/github_operations/test_github_write_tools_issues.py`
- `tests/github_operations/test_github_write_tools_issue_edit.py`
- `tests/github_operations/test_github_write_tools_issue_edit_base_branch.py`
- `tests/github_operations/test_github_write_tools_reference.py`
- `tests/github_operations/test_github_write_tools_subissues.py`
- `vulture_whitelist.py` — only if vulture flags a new name

## Steps

1. `format_rate_limit_error` + extra diagnostic headers (`_diagnostics.py`)
2. Fail-fast rate-limit cap (`_client.py`, `pyproject.toml`)
3. Shared login cache (`base_manager.py`, `__init__.py`, conftest fixture)
4. Rate-limit reporting and re-raise in `base_manager.py`
5. Server `@me` uses the shared cache; remove `server._login_cache`
6. Rate-limit replies in all `github_*` server tools

Each step = one commit: tests first, then implementation, then
pylint + pytest (`-n auto`) + mypy (+ lint-imports where noted) all green,
`run_format_code` before committing.
