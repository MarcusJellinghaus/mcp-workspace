
# Step 3 — `server.py`: build `ConversationCommentData` for conversation comments

Part of issue #310. Depends on Steps 1 and 2 (`ConversationCommentData` must
exist in `pr_manager.py`, and `format_pr_view()` must accept it). See
[summary.md](./summary.md) for full context.

## Precondition

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

If the function body does not match this shape, write one line to
`pr_info/.blocked.txt` describing the mismatch and stop.

## WHERE

- `src/mcp_workspace/server.py` (inside `github_pr_view()`)

## WHAT

Replace the lazy import of `CommentData` with `ConversationCommentData`,
imported directly from where it lives after Step 1:

```python
from mcp_workspace.github_operations.pr_manager import ConversationCommentData
```

Retype the local variable:

```python
conversation_comments: Optional[List[ConversationCommentData]] = None
```

## HOW

No decorator changes — `github_pr_view()` keeps its existing
`@mcp.tool()` / `@log_function_call` decorators. Only the lazy import block
and the one list-comprehension construction change.

## ALGORITHM

```
for c in repo.get_issue(number).get_comments():
    author = c.user.login
    created_at = c.created_at.isoformat() if c.created_at else None
    yield ConversationCommentData(id=c.id, body=c.body, author=author, created_at=created_at)
```

Drop `updated_at` and `url` entirely — `ConversationCommentData` has no such
fields.

## DATA

`conversation_comments` becomes `Optional[List[ConversationCommentData]]`,
each item `{"id": int, "body": str, "author": str, "created_at": Optional[str]}`,
passed unchanged into `format_pr_view(pr_dict, reviews, conversation_comments,
inline_comments, max_lines)`.

## Tests

No new test file needed — existing coverage in
`tests/github_operations/test_github_read_tools_pr_search.py`
(`test_github_pr_view_with_comments`) already exercises this code path via a
mocked PyGithub comment (`conv_comment.id`, `.body`, `.user.login`,
`.created_at.isoformat.return_value`) and asserts on rendered text
(`"Nice change"`), not on the removed `updated_at`/`user` keys, so it should
pass unchanged. Run it explicitly to confirm:

`mcp__mcp-tools-py__run_pytest_check` scoped to
`tests/github_operations/test_github_read_tools_pr_search.py`, then the full
suite with `extra_args: ["-n", "auto"]`, plus
`mcp__mcp-tools-py__run_pylint_check` and `mcp__mcp-tools-py__run_mypy_check`.
If `test_github_pr_view_with_comments` fails because it asserts on a dropped
field, update only that test's assertions — do not reintroduce
`updated_at`/`url`.

## Commit

One commit: `server.py` change (+ test fix only if the precondition above
turns out false), all checks green. Suggested message:

```
fix(server): github_pr_view builds ConversationCommentData

Match the retyped format_pr_view() parameter: construct
ConversationCommentData (author, no updated_at/url) instead of the
issue-comment CommentData shape.
```
