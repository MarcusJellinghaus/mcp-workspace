# Step 2 — `_pr_manager` helper + `reply_to_review_comment` + `github_review_comment_reply`

Read `pr_info/steps/summary.md` first for overall context. Depends on step 1
(`PullRequestManager(repo_url=...)`).

## Precondition check (do this before writing any code)

This step assumes PyGithub's `PullRequest` class exposes
`create_review_comment_reply(comment_id, body)` returning a `PullRequestComment`-like
object with `.id`, `.body`, `.user`, `.created_at`, `.updated_at`, `.html_url`. Verify
this with `mcp__mcp-tools-py__get_library_source` (library PyGithub, symbol
`PullRequest.create_review_comment_reply`) before implementing. If the method does not
exist, or its signature/return shape differs from this, stop and report the mismatch
to the user instead of implementing — do not guess an alternative API or write any
code for this step.

## Goal

Add the reply tool: `github_review_comment_reply(pr_number, comment_id, body,
reference_name=None)`. Add the `_pr_manager` helper it needs (also reused by step 3).

## WHERE

- `src/mcp_workspace/server.py` — new `_pr_manager` helper (near `_issue_manager`,
  server.py:813), new `github_review_comment_reply` tool (near `github_issue_comment`)
- `src/mcp_workspace/github_operations/pr_manager.py` — new `reply_to_review_comment`
  method, new `_validate_comment_id` helper method
- `.claude/CLAUDE.md` — tool-mapping table
- Tests: `tests/github_operations/test_pr_manager.py` (new method tests),
  `tests/github_operations/test_github_write_tools_labels_pr.py` (new tool test class)

## WHAT

```python
# server.py
def _pr_manager(reference_name: Optional[str]) -> "PullRequestManager": ...

@mcp.tool()
def github_review_comment_reply(
    pr_number: int,
    comment_id: int,
    body: str,
    reference_name: Optional[str] = None,
) -> str: ...
```

```python
# pr_manager.py
def _validate_comment_id(self, comment_id: int) -> bool: ...

def reply_to_review_comment(
    self, pr_number: int, comment_id: int, body: str
) -> CommentData: ...
```

## HOW

- `_pr_manager` mirrors `_issue_manager` exactly: lazy-import `PullRequestManager`
  inside the function (keeps PyGithub off the startup import path); `reference_name is
  None` → `PullRequestManager(project_dir=_project_dir)`; otherwise →
  `PullRequestManager(repo_url=get_reference_repo_url(reference_name))`. Add
  `PullRequestManager` to the `TYPE_CHECKING` import block alongside `IssueManager`.
- `_validate_comment_id` mirrors the existing `_validate_pr_number`/`_validate_branch_name`
  style in `pr_manager.py` exactly: `isinstance(comment_id, int) and comment_id > 0`,
  `logger.error(...)` and return `False` on failure — do **not** reuse
  `issues/base.py`'s raising `validate_comment_id`; every validator already in this
  class logs-and-swallows rather than raises, and this method should match its siblings.
- `reply_to_review_comment` is decorated `@log_function_call` +
  `@_handle_github_errors(default_return=<empty CommentData factory>)`, matching
  `create_pull_request`'s shape. Import `CommentData` from
  `mcp_workspace.github_operations.issues.types` — do not define a new TypedDict; the
  shape (id/body/user/created_at/updated_at/url) is identical to an issue comment.
- `github_review_comment_reply` follows `github_issue_comment`'s exact shape: try/except
  Exception → `f"Error: {e}"`; empty `id` on the returned `CommentData` → failure
  message; otherwise success message with the comment URL. Use `_ref_suffix` on the
  failure branch, matching `github_issue_comment`.

## ALGORITHM

```
# reply_to_review_comment
if not self._validate_pr_number(pr_number): return empty
if not self._validate_comment_id(comment_id): return empty
if not body or not body.strip(): log error; return empty
repo = self._get_repository(); if None: return empty
pr = repo.get_pull(pr_number)
reply = pr.create_review_comment_reply(comment_id, body.strip())
return CommentData(id=reply.id, body=reply.body or "",
                    user=reply.user.login if reply.user else None,
                    created_at=reply.created_at.isoformat() if reply.created_at else None,
                    updated_at=reply.updated_at.isoformat() if reply.updated_at else None,
                    url=reply.html_url)
```

```
# github_review_comment_reply
try:
    manager = _pr_manager(reference_name)
    reply = manager.reply_to_review_comment(pr_number, comment_id, body)
    if not reply["id"]:
        return f"Error: failed to reply to review comment {comment_id} on PR #{pr_number}{_ref_suffix(reference_name)}"
    return f"Replied to review comment {comment_id} on PR #{pr_number} — {reply['url']}"
except Exception as e:
    return f"Error: {e}"
```

## DATA

`reply_to_review_comment` returns `CommentData` (existing TypedDict from
`issues/types.py`): `{id, body, user, created_at, updated_at, url}`. Empty-failure
sentinel is the same `CommentData` with `id=0`, matching `CommentsMixin`'s convention.

## Tests (write first)

`tests/github_operations/test_pr_manager.py` — new tests for `reply_to_review_comment`
(mock `repo.get_pull(...).create_review_comment_reply(...)` via `create_mock_pr` plus a
`Mock()` reply object):
- success returns populated `CommentData`
- invalid `pr_number` → empty `CommentData`, no API call
- invalid `comment_id` (`<= 0`) → empty `CommentData`, no API call
- empty/whitespace `body` → empty `CommentData`, no API call
- repository unavailable → empty `CommentData`

`tests/github_operations/test_github_write_tools_labels_pr.py` — new
`TestGithubReviewCommentReply` class, patching
`mcp_workspace.github_operations.pr_manager.PullRequestManager` (same pattern as
`TestGithubPrCreate`), plus the `reference_projects` fixture pattern from
`test_github_write_tools_subissues.py` for the `reference_name` path:
- success message with URL
- failure (`id=0`) → error message
- exception from the manager → `"Error: {message}"`
- unknown `reference_name` → `"Error: Reference project 'nope' not found"`,
  manager class never constructed

## Commit

One commit covering `_pr_manager`, `reply_to_review_comment`, `_validate_comment_id`,
`github_review_comment_reply`, the CLAUDE.md row, and all tests above. Run pylint,
pytest (`-n auto`), mypy — all must pass.

Add to `.claude/CLAUDE.md`'s tool-mapping table, next to the `github_issue_comment` row:
`| Reply to inline PR review comment | mcp__mcp-workspace__github_review_comment_reply |`

Commit message: `feat(server): add github_review_comment_reply tool`

## LLM prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. First do the
> precondition check described there via `get_library_source`; if it fails, stop and
> report the mismatch instead of implementing. Otherwise implement step 2 only: the
> `_pr_manager` helper and `github_review_comment_reply` tool in `server.py`, and
> `reply_to_review_comment` / `_validate_comment_id` in `pr_manager.py`, following the
> WHERE/WHAT/HOW/ALGORITHM/DATA in step_2.md exactly. Write tests first, then the
> implementation. Update the `.claude/CLAUDE.md` tool table. Run pylint, pytest
> (`-n auto`), and mypy; all must pass. Make exactly one commit for this step. Do not
> touch step 3's resolve-thread logic.
