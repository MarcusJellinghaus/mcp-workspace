
# Step 2 — `formatters.py` + `server.py`: use `ConversationCommentData` for conversation comments

Part of issue #310. Depends on Step 1 (`ConversationCommentData` must exist
in `pr_manager.py`). See [summary.md](./summary.md) for full context.

This step was originally split into two (formatters.py, then server.py).
They were merged into one commit because `server.py` is the only caller
that builds the argument `format_pr_view()` consumes: retyping either file
alone leaves the full pytest suite red (a `KeyError` in
`test_github_pr_view_with_comments`) until the other is also done. Each
step is required to land with all checks green, so the two cannot be
committed independently.

## Precondition

Open `src/mcp_workspace/github_operations/formatters.py` and confirm
`format_pr_view()` has a parameter
`conversation_comments: Optional[list[CommentData]] = None` and its body
contains a loop reading `comment['user']` and `comment['created_at']`.

Open `src/mcp_workspace/server.py`, locate `github_pr_view()`, and confirm it
contains:

```python
from mcp_workspace.github_operations.issues.types import CommentData
...
conversation_comments: Optional[List[CommentData]] = None
...
conversation_comments = [
    CommentData(
        id=c.id,
        body=c.body,
        user=c.user.login,
        created_at=c.created_at.isoformat(),
        updated_at=c.updated_at.isoformat() if c.updated_at else None,
        url="",
    )
    for c in repo.get_issue(number).get_comments()
]
```

If either does not match, write one line to `pr_info/.blocked.txt`
describing the mismatch and stop.

## WHERE

- `src/mcp_workspace/github_operations/formatters.py`
- `src/mcp_workspace/server.py`
- `tests/github_operations/test_formatters.py`

## WHAT

In `formatters.py`, change the import at the top to also bring in
`ConversationCommentData`:

```python
from mcp_workspace.github_operations.pr_manager import ConversationCommentData
```

(`CommentData` import stays — `format_issue_view()` still uses it for issue
comments.)

Retype `format_pr_view()`'s signature:

```python
def format_pr_view(
    pr: dict[str, Any],
    reviews: Optional[list[ReviewData]] = None,
    conversation_comments: Optional[list[ConversationCommentData]] = None,
    inline_comments: Optional[list[InlineCommentData]] = None,
    max_lines: int = 200,
) -> str:
```

In `server.py`, replace the lazy import of `CommentData` with
`ConversationCommentData`, imported directly from where it lives after
Step 1:

```python
from mcp_workspace.github_operations.pr_manager import ConversationCommentData
```

Retype the local variable:

```python
conversation_comments: Optional[List[ConversationCommentData]] = None
```

No decorator changes in either file — `github_pr_view()` keeps its existing
`@mcp.tool()` / `@log_function_call` decorators, and `format_pr_view()`
keeps its existing call sites' positional/keyword structure.

## HOW

Before writing, check for an import cycle: `pr_manager.py` must not import
from `formatters.py` (it doesn't, as of Step 1) — if it does by the time
this step runs, write one line to `pr_info/.blocked.txt` and stop instead
of restructuring imports.

## ALGORITHM

In `formatters.py`'s `if conversation_comments:` block, change the key read
from the loop variable:

```
for comment in conversation_comments:
    render f"**{comment['author']}** ({comment['created_at']}):\n{comment['body']}"
```

(was `comment['user']` — `ConversationCommentData` has no `user` key).

In `server.py`'s `github_pr_view()`:

```
for c in repo.get_issue(number).get_comments():
    author = c.user.login
    created_at = c.created_at.isoformat() if c.created_at else None
    yield ConversationCommentData(id=c.id, body=c.body, author=author, created_at=created_at)
```

Drop `updated_at` and `url` entirely — `ConversationCommentData` has no such
fields.

## DATA

No change to `format_pr_view()`'s return value (a formatted string) — only
the input type and the one dict-key lookup change.

`conversation_comments` (in `server.py`) becomes
`Optional[List[ConversationCommentData]]`, each item
`{"id": int, "body": str, "author": str, "created_at": Optional[str]}`,
passed unchanged into `format_pr_view(pr_dict, reviews,
conversation_comments, inline_comments, max_lines)`.

## Tests (write first)

`tests/github_operations/test_formatters.py`:

- `_make_comment()` is shared: `TestFormatIssueView` also uses it (e.g.
  `test_format_issue_view_with_comments`, calling `_make_comment(user="alice",
  ...)`), consumed by `format_issue_view()`, which still reads
  `comment['user']` and is unchanged by this issue. Do not retype
  `_make_comment()` itself — leave it building `CommentData` with its
  existing `user` kwarg, untouched.

  Instead, add a separate helper for the PR-view tests:

  ```python
  def _make_conversation_comment(
      body: str = "Comment text",
      author: str = "commenter",
      created_at: str = "2024-01-03T00:00:00Z",
  ) -> ConversationCommentData:
      return ConversationCommentData(
          id=1, body=body, author=author, created_at=created_at
      )
  ```

  Import `ConversationCommentData` from
  `mcp_workspace.github_operations.pr_manager` alongside the existing
  `CommentData` import (still needed by `_make_issue`/`format_issue_view`
  tests).
- `test_format_pr_view_with_conversation_comments` keeps its existing
  assertions (`"**alice**"`, `"Looks good"`, etc.) — it already calls
  `_make_comment(body=..., user="alice", ...)`; switch that call to
  `_make_conversation_comment(body=..., author="alice", ...)`.

No new test file needed for the `server.py` side — existing coverage in
`tests/github_operations/test_github_read_tools_pr_search.py`
(`test_github_pr_view_with_comments`) already exercises this code path via a
mocked PyGithub comment (`conv_comment.id`, `.body`, `.user.login`,
`.created_at.isoformat.return_value`) and asserts on rendered text
(`"Nice change"`), not on the removed `updated_at`/`user` keys, so it should
pass unchanged. If it fails because it asserts on a dropped field, update
only that test's assertions — do not reintroduce `updated_at`/`url`.

Run `mcp__mcp-tools-py__run_pytest_check` (`extra_args: ["-n", "auto"]`),
`mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_mypy_check`.
All must pass before committing.

## Commit

One commit: tests + `formatters.py` change + `server.py` change, all checks
green. Suggested message:

```
fix(github_operations): use ConversationCommentData end-to-end for PR view

format_pr_view() and server.py's github_pr_view() were typed against the
issue-comment CommentData shape (user/updated_at/url) for data that's
actually conversation comments (author, no updated_at/url). Switch both
to ConversationCommentData so producer and consumer agree on shape.
```
