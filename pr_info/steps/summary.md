# Summary — #336: expose commenter trust, withhold untrusted PR feedback

## Goal

`check_branch_status` and `github_pr_view` print PR/issue text from anyone. On a public
repo a stranger's comment can steer an agent that edits code and posts under the owner's
account. This change attaches GitHub's `author_association` to every feedback item and
withholds untrusted text **in the tool output, before the model reads it**.

Trusted = association `OWNER` / `MEMBER` / `COLLABORATOR`, or login on the allowlist
`[github] trusted_commenters` in `~/.mcp_coder/config.toml`. Everything else (incl. a
missing association) is untrusted. Applied per comment. Always on, no opt-out, no env var.

## Architectural / design changes

- **Collection vs display split.**
  - The library (`PullRequestManager.get_pr_feedback`, `IssueManager.get_comments`, `_pr_to_data`)
    returns complete raw data plus the new `author_association` field. It makes no trust decision.
  - The MCP tool output (`format_pr_feedback`, `format_pr_view`, the ❌-note lookup in
    `collect_branch_status`) applies the trust rule.
- **One implementation of the rule.** The new module `github_operations/trust.py` holds:
  - `is_trusted_author(login, association, trusted) -> bool`
  - `normalize_author_association(value) -> Optional[str]` (non-`str` → `None`)

  `get_trusted_commenters()` lives in `config.py`. Both public functions are re-exported from
  `mcp_workspace.github_operations` for mcp_coder (#1257).
- **Allowlist source is outside every repo.** It comes from the user config file only, through
  a new `_read_config_list`. It fails closed: a wrong type or a non-string entry logs a warning
  and returns an empty set. No env-var override.
- **Formatters stay pure.** The allowlist is read once per collection pass or tool call and
  passed down as a `frozenset[str]` (a required `trusted` parameter). There are no per-item
  file reads.
  - Internal callers look it up at call time via `mcp_workspace.config`, so one test patch
    covers them all.
- **Filtering pattern (KISS).** Each list is split once at the top of the formatter
  (trusted kept, untrusted counted). The existing rendering loops then run unchanged on
  trusted items only. This means withheld items never count towards `_MAX_FEEDBACK_ITEMS`
  and never trigger `_FULL_TEXT_HINT`.
- **One withheld line.** The shared pure helper `format_withheld_line(counts)` in
  `formatters.py` renders `Withheld from untrusted authors: 2 threads, 1 review — review on GitHub`.
  - It has no ids, logins, paths or bodies.
  - In `github_pr_view` it is joined to the State line, so `max_lines` cannot cut it.
- **Verdicts unchanged.** `blocks_merge` and the "clean" check still use the full lists.
- **New TypedDict `ReviewThreadData`** replaces `dict[str, Any]` for unresolved threads.
  `author_association: Optional[str]` (a required key) is added to these existing TypedDicts:
  - `ConversationCommentData`, `ChangesRequestedData`, `PullRequestData`
  - `CommentData`
  - `ReviewData` / `InlineCommentData`
- **Ghost users** (deleted accounts, `user is None`): the login becomes `None`, or `""` where the
  type is `str`. They are untrusted and must not cause a crash.

## Out of scope

CI failure log excerpt, head branch name (shown unchanged), `github_issue_view` and the
malformed `### Base Branch` line (→ #342), agent workflow policy (→ mcp_coder#1257).

## Files

Created:
- `src/mcp_workspace/github_operations/trust.py`
- `tests/github_operations/test_trust.py`

Modified (source):
- `src/mcp_workspace/config.py` — `_read_config_list`, `get_trusted_commenters`, logger
- `src/mcp_workspace/github_operations/__init__.py` — re-exports
- `src/mcp_workspace/github_operations/pr_types.py` — `ReviewThreadData`, new fields
- `src/mcp_workspace/github_operations/issues/types.py` — `CommentData.author_association`
- `src/mcp_workspace/github_operations/formatters.py` — `ReviewData`/`InlineCommentData` fields,
  `format_withheld_line`, `format_pr_view(trusted=...)`
- `src/mcp_workspace/github_operations/_pr_feedback_sources.py` — GraphQL `authorAssociation`, REST mapping
- `src/mcp_workspace/github_operations/pr_manager.py` — `_pr_to_data`
- `src/mcp_workspace/github_operations/issues/comments_mixin.py` — all `CommentData` sites
- `src/mcp_workspace/github_operations/pr_review_mixin.py` — `CommentData` sites
- `src/mcp_workspace/checks/pr_feedback.py` — `format_pr_feedback` / `collect_pr_feedback(trusted)`
- `src/mcp_workspace/checks/branch_status.py` — read allowlist, filter ❌-note comments, pass `trusted`
- `src/mcp_workspace/server.py` — `github_pr_view`: `pr_dict` user/association, ghost-safe items, `trusted`
- `README.md` — new "GitHub configuration" section

Modified (tests): `tests/conftest.py`, `tests/test_config.py`,
`tests/checks/test_branch_status_pr_feedback.py`, `tests/checks/test_branch_status.py`,
`tests/github_operations/test_formatters.py`, `tests/github_operations/test_pr_feedback_mixin.py`,
`tests/github_operations/_github_read_tools_helpers.py`,
`tests/github_operations/test_github_read_tools_pr_search.py`,
`tests/github_operations/test_github_write_tools_issues.py`,
`tests/github_operations/test_github_write_tools_reference.py`,
`tests/github_operations/issues/test_comments_mixin.py`, plus any other test that builds
one of the changed TypedDicts or calls a function that gained `trusted` (mypy will list them).

## Steps

1. Config + trust helpers + README (foundation, no behaviour change)
2. `author_association` on all data types and collection paths (no behaviour change)
3. `check_branch_status` gate (`format_pr_feedback`, ❌ note)
4. `github_pr_view` gate (title/body, reviews, comments, inline comments, ghost users)
