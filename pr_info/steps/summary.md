
# Summary — Add `id`/`created_at` to `PRFeedback.conversation_comments`

Issue: #310

## Problem

`fetch_conversation_comments()` builds each conversation-comment dict from a
PyGithub `IssueComment` but only copies `author`/`body`, discarding `c.id`
and `c.created_at`. Downstream work (mcp-coder#1188) needs `created_at` as a
watermark to tell an already-processed comment from a new one.

## Design changes

- **New `ConversationCommentData` TypedDict** (`pr_manager.py`, next to
  `PRFeedback`): `author: str`, `body: str`, `id: int`,
  `created_at: Optional[str]`. All four keys are **required** (not
  `NotRequired`) — `created_at` is realistically never `None` for a real
  comment, but its *value* type is `Optional[str]` to match the house
  `.isoformat() if x else None` convention used for every other datetime
  field in this codebase (`pr.created_at`, CI job timestamps). Keeping the
  key required means a consumer can always read it without a `.get()`
  fallback; only the value can be `None`.
- **`PRFeedback.conversation_comments`** changes from `list[dict[str, Any]]`
  to `list[ConversationCommentData]`.
- **Pre-existing type mismatch fixed in the same change**: `formatters.py`
  and `server.py` both currently (mis)type the conversation-comments
  parameter/variable as `Optional[list[CommentData]]`, where `CommentData`
  (`issues/types.py`) describes an *issue* comment (`id`, `body`, `user`,
  `created_at`, `updated_at`, `url`) — a different shape (no `author`, no
  `updated_at`/`url`). Both switch to `Optional[list[ConversationCommentData]]`.
  This is a real behavior-adjacent fix, not just an annotation swap:
  `formatters.py` indexes `comment['user']` and must read `comment['author']`
  instead; `server.py` constructs `CommentData(..., user=..., updated_at=...,
  url=...)` and must construct `ConversationCommentData(..., author=...)`,
  dropping the fields `ConversationCommentData` doesn't have.
- No change to existing `author`/`body` keys or consumer-facing behavior
  beyond the two added fields.

## Why not simpler alternatives

- Reusing `CommentData` would keep the existing shape mismatch (it has
  `user`/`updated_at`/`url`, not `author`).
- Loosening to `dict[str, Any]` would lose the type safety this issue exists
  to add, and wouldn't force the `formatters.py`/`server.py` fix.

## Files created / modified

| File | Change |
|---|---|
| `src/mcp_workspace/github_operations/pr_manager.py` | New `ConversationCommentData` TypedDict; `PRFeedback.conversation_comments` retyped |
| `src/mcp_workspace/github_operations/_pr_feedback_sources.py` | `fetch_conversation_comments()` adds `id`/`created_at`; return type updated |
| `src/mcp_workspace/github_operations/formatters.py` | `format_pr_view()` parameter retyped; `comment['user']` → `comment['author']` |
| `src/mcp_workspace/server.py` | Local `conversation_comments` variable retyped; construction switches to `ConversationCommentData` |
| `tests/github_operations/test_pr_manager_feedback.py` | `_make_comment()` helper sets explicit `id`/`created_at`; new assertions |
| `tests/checks/test_branch_status_pr_feedback.py` | `_comment()` helper extended to satisfy the stricter `PRFeedback` type |
| `tests/github_operations/test_formatters.py` | `_make_comment()` helper switched to build `ConversationCommentData` |

No new files/modules. No directory structure changes.

## Implementation steps

1. [step_1.md](./step_1.md) — `ConversationCommentData` TypedDict + `fetch_conversation_comments()` + `PRFeedback` retype (core data model).
2. [step_2.md](./step_2.md) — `formatters.py` + `server.py`: retype `format_pr_view()`'s parameter (`comment['user']` → `comment['author']`) and `server.py`'s construction, together in one commit.

Each step is one commit: tests + implementation + all checks (pylint, pytest, mypy) passing.

Steps 2 and 3 were originally separate (one file each) but were merged: `server.py`
is the only caller that builds the argument `format_pr_view()` consumes, so retyping
either file alone leaves the full pytest suite red until the other is done too — each
step requires a green suite before it can be committed.
