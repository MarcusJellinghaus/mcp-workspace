# Summary — PullRequestManager.update_pull_request (#349)

## Goal

Let callers edit an existing PR's title and/or body through `PullRequestManager`.
mcp-coder can't call PyGithub directly (import-linter `github_library_isolation`),
so it needs this method to refresh a PR description after pushing more commits
(unblocks MarcusJellinghaus/mcp_coder#1286).

## Architectural / design changes

- **One new public manager method:** `PullRequestManager.update_pull_request(pr_number, title=None, body=None) -> PullRequestData`.
- **No new modules, types or MCP tools.** It reuses the existing building blocks:
  `@log_function_call`, `@_handle_github_errors(cast(PullRequestData, {}))`,
  `_validate_pr_number`, `_get_repository`, `_pr_to_data`.
- **Pattern:** same as `close_pull_request` (edit, then re-fetch via a second
  `get_pull`). When there is nothing to edit it behaves like `add_assignees`
  (single `get_pull`, returns current data).
- **Semantics:**
  - `None` = unchanged. Only non-None fields are passed to `pr.edit(**fields)`.
    `None` is never forwarded, so PyGithub's `NotSet` defaults stay intact.
  - `body=""` is a real edit (clears the description).
  - `title` is stripped, as in `IssueManager.edit_issue`.
  - A supplied title that is blank after stripping raises
    `ValueError("Pull request title cannot be empty")`. This check runs
    before `_validate_pr_number` and `_get_repository`. The decorator re-raises `ValueError`.
  - Invalid PR number, unavailable repo, or a non-auth `GithubException` → `{}`.
    401/403/rate-limit propagate via the shared decorator (not re-tested).
  - Both fields `None` → no `edit`, no re-fetch, returns current PR data (non-empty).

## Files

| Action | Path |
|--------|------|
| Modify | `src/mcp_workspace/github_operations/pr_manager.py` |
| Create | `tests/github_operations/test_pr_manager_update_pull_request.py` |

No changes to docs, `server.py`, vulture whitelist, or architecture config.

## Steps

1. [step_1.md](./step_1.md) — tests + `update_pull_request` implementation (one commit).
