
# Step 1 — `ConversationCommentData` TypedDict + `fetch_conversation_comments()` + `PRFeedback` retype

Part of issue #310. See [summary.md](./summary.md) for full context and
rationale before starting.

## Precondition

Open `src/mcp_workspace/github_operations/pr_manager.py` and confirm:
- `PRFeedback` is a `TypedDict` with a `conversation_comments: list[dict[str, Any]]` field.
- `_empty_pr_feedback()` returns a dict literal including `"conversation_comments": []`.

Open `src/mcp_workspace/github_operations/_pr_feedback_sources.py` and confirm
`fetch_conversation_comments()` returns a list of `{"author": ..., "body": ...}`
dicts built from `issue.get_comments()`.

If either file's structure does not match, write one line to
`pr_info/.blocked.txt` describing the mismatch and stop.

## WHERE

- `src/mcp_workspace/github_operations/pr_manager.py`
- `src/mcp_workspace/github_operations/_pr_feedback_sources.py`
- `tests/github_operations/test_pr_manager_feedback.py`
- `tests/checks/test_branch_status_pr_feedback.py`

## WHAT

In `pr_manager.py`, add a new TypedDict directly above `PRFeedback`:

```python
class ConversationCommentData(TypedDict):
    """TypedDict for a PR top-level conversation comment."""

    author: str
    body: str
    id: int
    created_at: Optional[str]
```

Change `PRFeedback.conversation_comments` from `list[dict[str, Any]]` to
`list[ConversationCommentData]`.

In `_pr_feedback_sources.py`, update `fetch_conversation_comments()`:

```python
def fetch_conversation_comments(
    manager: "PullRequestManager", pr_number: int
) -> list["ConversationCommentData"]:
```

(import `ConversationCommentData` under `TYPE_CHECKING` from `.pr_manager`,
matching the existing `PullRequestManager` import there).

## HOW

No new decorators or call sites. `fetch_conversation_comments()` is only
called from `PullRequestManager.get_pr_feedback()`, which already assigns its
result straight into `PRFeedback["conversation_comments"]` — no caller change
needed there.

## ALGORITHM

In the list comprehension inside `fetch_conversation_comments()`, add two
keys to the dict built per comment `c`:

```
for c in comments:
    author = c.user.login if c.user else ""
    body = c.body or ""
    id = c.id
    created_at = c.created_at.isoformat() if c.created_at else None
    yield {author, body, id, created_at}
```

## DATA

Each dict in the returned list now has exactly four keys:
`{"author": str, "body": str, "id": int, "created_at": Optional[str]}`.

## Tests (write first)

1. `tests/github_operations/test_pr_manager_feedback.py`:
   - `_make_comment(self, login: str, body: str) -> Mock` — add explicit
     `comment.id = <deterministic int>` and
     `comment.created_at.isoformat.return_value = <deterministic ISO string>`
     so the mock no longer relies on auto-generated `Mock()` attributes.
   - In `test_happy_path`, after the existing assertions on
     `result["conversation_comments"][0]["author"]` / `["body"]`, add
     assertions on `["id"]` and `["created_at"]` matching the values set in
     `_make_comment`.
   - Add a focused unit test for `fetch_conversation_comments()` itself
     (alongside the existing tests in that area) asserting the returned dict
     has all four keys with the right values, including the `created_at is
     None` case when `c.created_at` is falsy.

2. `tests/checks/test_branch_status_pr_feedback.py`:
   - `_comment()` helper currently returns `dict[str, Any]` with only
     `author`/`body`. Extend its signature to
     `_comment(author: str = "bob", body: str = "Looks good", comment_id: int = 1, created_at: str | None = "2024-01-01T00:00:00") -> dict[str, Any]`
     and include `id`/`created_at` in the returned dict, so every call site
     (`feedback["conversation_comments"] = [_comment(...)]`) satisfies
     `list[ConversationCommentData]`. No call sites need their arguments
     changed — only the helper's return shape.

Run `mcp__mcp-tools-py__run_pytest_check` (with `extra_args: ["-n", "auto"]`),
`mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_mypy_check`.
All must pass before committing.

## Commit

One commit: tests + `pr_manager.py` + `_pr_feedback_sources.py` changes, all
checks green. Suggested message:

```
feat(github_operations): add id/created_at to conversation comments

Add ConversationCommentData TypedDict and carry PyGithub's id/created_at
through fetch_conversation_comments(), needed by mcp-coder#1188 for
comment-age watermarking.
```
