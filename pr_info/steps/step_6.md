# Step 6 — Rate-limit replies in all `github_*` server tools

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_6.md`), and issue #329
> (section "Rate-limit error message", "Server tools") for context. Implement **only** this
> step with TDD: write the tests below first, then the implementation. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`), mypy and lint-imports; all must pass. Run
> `run_format_code`, then make exactly one commit.

## WHERE

- `src/mcp_workspace/server.py`
- `tests/github_operations/test_github_write_tools_issues.py`
- `tests/github_operations/test_github_write_tools_issue_edit.py`
- `tests/github_operations/test_github_write_tools_reference.py`

## WHAT

```python
def _tool_error(e: Exception) -> str:
    """Render a tool failure, naming bucket and reset time for a rate limit."""
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations import format_rate_limit_error
    return format_rate_limit_error(e) or f"Error: {e}"
```

Place it next to `_api_error`.

## HOW

1. Replace `return f"Error: {e}"` in the outer `except Exception as e` of each of these tools
   with `return _tool_error(e)`: `github_issue_view`, `github_issue_list`, `github_pr_view`,
   `github_search`, `github_issue_create`, `github_issue_edit`, `github_issue_comment`,
   `github_review_comment_reply`, `github_review_thread_resolve`, `github_label_list`,
   `github_pr_create`. Do **not** touch the non-`github_*` tools (e.g. `check_branch_status`,
   `get_base_branch`, file/git tools).
2. `_api_error`: first line `if (msg := format_rate_limit_error(exc)) is not None: return f"{msg}{_ref_suffix(reference_name)}"`;
   the rest unchanged (don't move other sites onto `_api_error`).
3. Widen to catch `RetryError` (import alongside the existing lazy `GithubException` import:
   `from mcp_workspace.github_operations import GithubException, RetryError`):
   - `github_issue_edit` inner `except (GithubException, ValueError)` →
     `except (GithubException, RetryError, ValueError)`;
   - `_subissue_write` and `github_subissue_list` `except (GithubException, ValueError)` → same.
4. `github_issue_edit`: `reason = format_rate_limit_error(exc) or str(exc)` in the inner
   except, and `reread_error = f": {format_rate_limit_error(exc) or exc}"` in the re-read
   except.
5. Never `import requests` in `server.py` (import-linter "Requests Library Isolation").

## DATA

- Tool replies stay `str`. Rate-limit replies are the `format_rate_limit_error` text
  (plus reference suffix in `_api_error`); everything else is byte-identical to today.

## Tests (write first)

Shared rate-limit fixture: `GithubException(403, {"message": "API rate limit exceeded"},
{"x-ratelimit-remaining": "0", "x-ratelimit-resource": "core", "x-ratelimit-reset": str(reset)})`
with `reset = int(time.time()) + 600`; expected `HH:MM` derived from `reset`.

- `github_issue_create` and `github_issue_edit`: patch `IssueManager` so the tool's call
  raises the 403 rate limit (simulate `get_repo` inside `_get_repository` re-raising — e.g.
  `create_issue.side_effect` / `get_available_labels.side_effect`) → reply contains
  `` `core` `` and the `HH:MM`, and not "Could not access repository" / "issue creation failed".
- `github_subissue_list` and `github_subissue_add` (in `test_github_write_tools_reference.py`
  or the issues file): `list_sub_issues` / `add_sub_issue` raising
  `requests.exceptions.RetryError("x")` → reply is the rate-limit message
  ("retries exhausted"), no exception escapes.
- `github_issue_edit`: `edit_issue` records a write in `attempted_writes` then raises
  `RetryError` (reuse `_recording_edit_issue([...], error=RetryError("x"))`), `get_issue`
  returns the re-read issue → reply starts with "Warning: edit partially failed" and contains
  "retries exhausted".
- One read tool (e.g. `github_issue_view` or `github_label_list`) raising the 403 rate limit →
  reply names `` `core` `` (guards the `_tool_error` wiring).
- Existing tests asserting `result.startswith("Error:")` for non-rate-limit errors stay green.
