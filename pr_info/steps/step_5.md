# Step 5 — Server `@me` uses the shared login cache

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_5.md`), and issue #329
> (section "Shared login cache", server bullet) for context. Implement **only** this step with
> TDD: update the tests below first, then the implementation. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`), mypy, lint-imports and vulture; all must pass. Run
> `run_format_code`, then make exactly one commit.

## WHERE

- `src/mcp_workspace/server.py`
- `tests/github_operations/test_github_write_tools_issues.py`
- `tests/github_operations/test_github_write_tools_issue_edit.py`
- `tests/github_operations/test_github_write_tools_issue_edit_base_branch.py`
- `tests/github_operations/test_github_write_tools_reference.py`

## WHAT

```python
def _resolve_assignees(manager: Any, logins: List[str]) -> List[str]:
    """Resolve '@me' to the authenticated login, cached per GitHub host and token."""
```

- Delete `server._login_cache` and its comment block; drop `Dict` from the `typing` import if
  it becomes unused.

## HOW

- Lazy import inside `_resolve_assignees`, matching the file's style:
  `from mcp_workspace.github_operations.base_manager import _cached_login`
- Must use the manager's token and client, not `get_github_token()`; keep the comment
  explaining that.

## ALGORITHM

```
if "@me" not in logins: return list(logins)
# pylint: disable=protected-access
login = _cached_login(manager.github_token,
                      manager._repo_identifier.api_base_url,
                      manager._github_client)
return [login if name == "@me" else name for name in logins]
```

## DATA

- Unchanged return type; a failed lookup propagates (`GithubException`), as today.

## Tests (write first)

- Delete the per-file `reset_login_cache` fixtures in
  `test_github_write_tools_issues.py`, `test_github_write_tools_issue_edit.py` and
  `test_github_write_tools_issue_edit_base_branch.py` (the conftest autouse fixture from step 3
  now covers them). Remove imports that become unused (`server_module`, `Generator`).
- Add `mock_mgr.github_token = "test-token"` to `_make_manager` in those three files and in
  `test_github_write_tools_reference.py` (sha256 of a `MagicMock` raises `TypeError`).
- Existing tests `test_github_issue_create_caches_me_lookup`,
  `test_github_issue_create_me_lookup_is_per_host` and
  `test_github_issue_create_explicit_assignee_skips_lookup` must pass unchanged.
- New: two managers on the same host with different `github_token` values each resolve
  `@me` themselves (token is part of the key).
