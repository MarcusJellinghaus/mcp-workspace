
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

- `_make_comment()` currently builds `CommentData(id=1, body=..., user=...,
  created_at=..., updated_at=None, url=...)`. Change it to build
  `ConversationCommentData`:

  ```python
  def _make_comment(
      body: str = "Comment text",
      author: str = "commenter",
      created_at: str = "2024-01-03T00:00:00Z",
  ) -> ConversationCommentData:
      return ConversationCommentData(
          id=1, body=body, author=author, created_at=created_at
      )
  ```

  and import `ConversationCommentData` from `mcp_workspace.github_operations.pr_manager`
  instead of using `CommentData` for this helper. Keep `CommentData` imported
  if `_make_issue`/`format_issue_view` tests in the same file still need it.
- `test_format_pr_view_with_conversation_comments` keeps its existing
  assertions (`"**alice**"`, `"Looks good"`, etc.) — it already calls
  `_make_comment(body=..., user="alice", ...)`; update the call to pass
  `author="alice"` instead of `user="alice"` to match the new helper
  signature.

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
