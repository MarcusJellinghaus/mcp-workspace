# Implementation Summary — Issue #308: Reply to and resolve inline PR review comments

## Problem

Two gaps in `mcp-workspace`'s GitHub tooling, both needed for an automated "PR needs
attention" workflow in `mcp-coder`:

1. No tool replies to an **inline PR review comment** (a comment on a specific diff
   line, part of a review thread) — distinct from `github_issue_comment`, which only
   covers top-level PR conversation comments.
2. No tool **resolves** a review thread, so an automated session that addresses a
   thread has no way to clear its unresolved state.

Both tools need IDs that nothing currently surfaces: `/check_branch_status`'s
`[unresolved thread]` lines show path/line/author/body but no comment or thread ID.

## Architectural / design changes

- **`PullRequestManager` gains dual-mode construction.** `__init__` adds a `repo_url`
  parameter, mirroring `IssueManager`/`CIResultsManager` (both already support
  `project_dir` *or* `repo_url`). The existing fail-fast "no GitHub remote" check stays,
  but only runs in `project_dir` mode — it never applied to `repo_url` mode even before
  this change, since `_repo_identifier` is already resolved synchronously by the base
  class for that mode.
- **`server.py` gains a `_pr_manager(reference_name)` helper**, mirroring `_issue_manager`:
  builds a `PullRequestManager` against the workspace repo (`reference_name=None`) or a
  reference project's repo (`reference_name` set). Only the two new tools use it; the
  existing `github_pr_create` / `get_base_branch` call sites are untouched.
- **Two new `PullRequestManager` methods**, each with a matching MCP tool:
  - `reply_to_review_comment(pr_number, comment_id, body)` — thin wrapper around
    PyGithub's `PullRequest.create_review_comment_reply()`. No PR/comment cross-check:
    GitHub's REST endpoint is nested under `pull_number`, so a `comment_id` from another
    PR is rejected by GitHub itself.
  - `resolve_review_thread(pr_number, thread_id)` — the `resolveReviewThread` GraphQL
    mutation, issued via the same raw `Requester.graphql_query()` call `get_closing_issue_numbers`
    already uses (raises on error, no retry — unlike `fetch_review_data`'s retry-wrapped
    `requestJsonAndCheck`, whose retry exists only for a read-after-write flake that does
    not apply to a one-shot mutation).
- **Design decision — thread/PR validation via a targeted `node(id:)` lookup.** Before
  resolving, the method confirms `thread_id` belongs to `pr_number` with a single
  GraphQL query: `node(id: $threadId) { ... on PullRequestReviewThread { isResolved
  pullRequest { number } } }`. This returns exactly the three facts needed —
  not-found (`node` is `null`), wrong PR (`pullRequest.number != pr_number`), already
  resolved (`isResolved`) — in one targeted request, instead of listing the PR's whole
  `reviewThreads(first: 50)` collection and searching client-side.
- **ID visibility.** `_pr_feedback_sources.fetch_review_data`'s GraphQL query gains
  `databaseId` on review comments (the REST comment ID the reply tool needs) and `id`
  on thread nodes (the GraphQL thread ID the resolve tool needs). Both are threaded into
  each `unresolved_threads` entry. `checks/pr_feedback.py`'s `format_pr_feedback` renders
  both in its `[unresolved thread]` lines. Resolved threads stay count-only — the issue
  scopes rendering to unresolved threads only; the resolve tool's own validation uses its
  independent `node(id:)` lookup, not this data.

## Files created / modified

| File | Change |
|---|---|
| `src/mcp_workspace/github_operations/pr_manager.py` | `__init__` gains `repo_url`; new `reply_to_review_comment`, `resolve_review_thread`, `_validate_comment_id` methods; import `CommentData` from `issues/types.py` |
| `src/mcp_workspace/github_operations/_pr_feedback_sources.py` | `fetch_review_data`'s GraphQL query gains `databaseId`/`id`; `unresolved_threads` entries gain `comment_id`/`thread_id` |
| `src/mcp_workspace/checks/pr_feedback.py` | `format_pr_feedback` renders `comment_id`/`thread_id` in `[unresolved thread]` lines |
| `src/mcp_workspace/server.py` | New `_pr_manager(reference_name)` helper; two new `@mcp.tool()` functions: `github_review_comment_reply`, `github_review_thread_resolve` |
| `.claude/CLAUDE.md` | Two new rows in the tool-mapping table |
| `tests/github_operations/test_pr_manager.py` | Constructor tests for `repo_url` |
| `tests/github_operations/test_pr_manager_review_reply.py` (new) | Unit tests for `reply_to_review_comment` |
| `tests/github_operations/test_pr_manager_review_resolve.py` (new) | Unit tests for `resolve_review_thread` |
| `tests/github_operations/test_github_write_tools_labels_pr.py` | New test classes for the two MCP tools (reused file — it already covers PR-related write tools) |
| `tests/github_operations/test_pr_manager_feedback.py` | Updated GraphQL fixtures + assertions for `comment_id`/`thread_id` |
| `tests/checks/test_branch_status_pr_feedback.py` | Updated rendering assertions for `comment_id`/`thread_id` |

## Steps

1. `step_1.md` — `PullRequestManager` constructor: add `repo_url` support
2. `step_2.md` — `_pr_manager` helper + `reply_to_review_comment` + `github_review_comment_reply` tool
3. `step_3.md` — `resolve_review_thread` + `github_review_thread_resolve` tool
4. `step_4.md` — `fetch_review_data`: surface `comment_id`/`thread_id`
5. `step_5.md` — `format_pr_feedback`: render `comment_id`/`thread_id`

Each step is one commit: tests written first, then the implementation that makes them
pass, then quality checks (`run_pylint_check`, `run_pytest_check` with
`extra_args: ["-n", "auto"]`, `run_mypy_check`) — all must pass before moving on.
