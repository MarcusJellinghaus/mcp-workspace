
# Step 2 — `formatters.py`: retype `format_pr_view()`'s conversation-comments parameter

Part of issue #310. Depends on Step 1 (`ConversationCommentData` must exist
in `pr_manager.py`). See [summary.md](./summary.md) for full context.

## Precondition

Open `src/mcp_workspace/github_operations/formatters.py` and confirm
`format_pr_view()` has a parameter
`conversation_comments: Optional[list[CommentData]] = None` and its body
contains a loop reading `comment['user']` and `comment['created_at']`.

If the signature or body does not match, write one line to
`pr_info/.blocked.txt` describing the mismatch and stop.

## WHERE

- `src/mcp_workspace/github_operations/formatters.py`
- `tests/github_operations/test_formatters.py`

## WHAT

Change the import at the top of `formatters.py` to also bring in
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

## HOW

No decorator or call-site changes outside this function body. Check for an
import cycle before writing: `pr_manager.py` must not import from
`formatters.py` (it doesn't, as of Step 1) — if it does by the time this
step runs, write one line to `pr_info/.blocked.txt` and stop instead of
restructuring imports.

## ALGORITHM

In the `if conversation_comments:` block, change the key read from the loop
variable:

```
for comment in conversation_comments:
    render f"**{comment['author']}** ({comment['created_at']}):\n{comment['body']}"
```

(was `comment['user']` — `ConversationCommentData` has no `user` key).

## DATA

No change to the function's return value (a formatted string) — only the
input type and the one dict-key lookup change.

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

Run `mcp__mcp-tools-py__run_pytest_check` (`extra_args: ["-n", "auto"]`),
`mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_mypy_check`.
All must pass before committing.

## Commit

One commit: test + `formatters.py` change, all checks green. Suggested
message:

```
fix(github_operations): format_pr_view uses ConversationCommentData

format_pr_view() was typed against the issue-comment CommentData shape
(user/updated_at/url) for a parameter that actually receives conversation
comments (author, no updated_at/url). Switch to ConversationCommentData.
```
