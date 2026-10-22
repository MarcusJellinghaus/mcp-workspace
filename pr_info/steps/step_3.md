# Step 3 — Collect timestamps, HEAD and the stale verdict

Read `pr_info/steps/summary.md` first. Requires Steps 1 and 2. One commit: tests + implementation,
all checks passing.

## LLM prompt

> Implement Step 3 of `pr_info/steps/summary.md` as described in `pr_info/steps/step_3.md`.
> Write the collection tests first, then the code. Run pylint, mypy, pytest (`-n auto`), tach and
> lint-imports; check `branch_status.py` stays ≤ 750 lines; format code; commit once.

## Precondition

If `get_head_commit_info` is not importable from `mcp_workspace.git_operations.commits` or
`BranchStatusReport` has no `marked_comment_stale` field, write one line to `pr_info/.blocked.txt`
and stop.

## WHERE

- `tach.toml` — `mcp_workspace.checks` `depends_on`: add `{ path = "mcp_workspace.utils" }`
- `src/mcp_workspace/checks/branch_status.py` — new private helper + wiring in `collect_branch_status`
- `tests/checks/test_branch_status.py`

## WHAT

```python
def _marked_comment_context(
    project_dir: Path, comment: CommentData
) -> tuple[Optional[datetime], Optional[str], Optional[datetime], bool]:
    """Return (created_at, head_short_sha, head_committed_at, stale) for a marked comment.

    Never raises: an exception here would replace the whole report with the
    empty fallback. Stale only when both timestamps exist and the comment is
    strictly older than HEAD's committer date (second precision; a tie is current).
    """
```

## HOW

- Imports in `branch_status.py`:
  `from mcp_workspace.git_operations.commits import get_head_commit_info`
  `from mcp_workspace.utils.timezone_utils import parse_iso_timestamp`
  (Import `get_head_commit_info` into this module's namespace — tests patch
  `mcp_workspace.checks.branch_status.get_head_commit_info`.)
- Place the helper before `collect_branch_status`.
- In `collect_branch_status`, after the GitHub try block (step 2), only when a comment was found:

```python
marked_created_at, head_short_sha, head_committed_at, marked_stale = (
    _marked_comment_context(project_dir, last_marked_comment)
    if last_marked_comment is not None
    else (None, None, None, False)
)
```

  Pass the four values to the `BranchStatusReport` constructor.

## ALGORITHM

```
created = None
if comment["created_at"]:
    try: created = parse_iso_timestamp(comment["created_at"])
    except ValueError: logger.debug("Unparseable comment created_at: %r", ...)
head = get_head_commit_info(project_dir)
sha, committed = head if head is not None else (None, None)
return created, sha, committed, created is not None and committed is not None and created < committed
```

## DATA

Tuple `(Optional[datetime], Optional[str], Optional[datetime], bool)` → the four report fields
`marked_comment_created_at`, `head_short_sha`, `head_committed_at`, `marked_comment_stale`.

## Tests (`tests/checks/test_branch_status.py`)

- `_issue_comment(comment_id, body, association, created_at: str | None = None)` — pass through to
  `CommentData(created_at=...)`.
- `_note_with_comments(comments, head: tuple[str, datetime] | None = None)` → returns the full
  `BranchStatusReport` (rename to `_report_with_comments`); adds
  `patch(f"{mod}.get_head_commit_info", return_value=head)` to its `with` block. Update the two
  existing callers to read `.last_marked_comment`.
- New tests, each with one trusted (`"OWNER"`) ❌ comment and
  `head = ("abc1234", datetime(2026, 10, 22, 7, 12, 40, tzinfo=timezone.utc))`:

| Test | `created_at` | `head` | Expect |
|------|-------------|--------|--------|
| stale | `"2026-10-22T04:58:13Z"` | head | `marked_comment_stale is True`; `marked_comment_created_at` == parsed UTC; `head_short_sha == "abc1234"`; `head_committed_at` == head datetime |
| current | `"2026-10-22T09:30:05Z"` | head | `marked_comment_stale is False` |
| tie | `"2026-10-22T07:12:40Z"` | head | `marked_comment_stale is False` |
| HEAD unavailable | `"2026-10-22T04:58:13Z"` | `None` | `head_short_sha is None`, `head_committed_at is None`, not stale, `marked_comment_created_at` set |
| unparseable created_at | `"not-a-date"` | head | `marked_comment_created_at is None`, not stale, `last_marked_comment` still set, report not the empty fallback (`branch_name == "123-feature"`) |

Existing tests that don't mock HEAD need no change beyond Step 2's rename.
