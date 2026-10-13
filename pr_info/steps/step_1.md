# Step 1: `find_latest_marked_comment` pure helper

Reference: `pr_info/steps/summary.md` (issue #309). This is step 1 of 3 — the pure scan
helper, with no collector or rendering wiring yet.

## Precondition

`src/mcp_workspace/github_operations/formatters.py` must already define `truncate_output`,
`format_issue_view`, `format_pr_view` taking `list[CommentData]`, and import `CommentData`
from `mcp_workspace.github_operations.issues.types`. If the module's shape differs from
this, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/formatters.py` — add the function.
- `tests/github_operations/test_formatters.py` — add the tests (existing file; add a new
  test class, do not create a new test module).

## WHAT

```python
def find_latest_marked_comment(
    comments: List[CommentData], marker: str = "❌", window: int = 3
) -> Optional[str]:
    """Return the full body of the most recent comment marked with `marker`.

    Scans the last `window` comments, most-recent-first, for the first whose
    first line contains `marker` as a substring (not a prefix — the marker
    may sit inside a markdown heading, e.g. "## ❌ Implementation Failed").

    Args:
        comments: Issue comments, oldest-first (as returned by get_comments).
        marker: Substring to look for on the first line of a comment body.
        window: How many of the most recent comments to scan.

    Returns:
        The full matched comment body, or None if no comment in the window matches.
    """
```

Add `List` to the existing `from typing import Any, Optional, TypedDict` import line.

## HOW

Top-level public function in `formatters.py`, next to the other `format_*`/`truncate_*`
functions. No new imports beyond `List` (already imports `CommentData`). No changes to any
existing function in the file.

## ALGORITHM

```
for comment in reversed(comments[-window:]):      # most-recent-first within window
    body = comment["body"]
    if not body:                                   # "".splitlines() == [] — guard first
        continue
    if marker in body.splitlines()[0]:             # substring test, not startswith
        return body
return None
```

## DATA

Returns `Optional[str]`: the full, unmodified `body` of the matched `CommentData`, or
`None` when nothing in the window matches.

## Tests (write first)

New class in `tests/github_operations/test_formatters.py`, e.g. `TestFindLatestMarkedComment`,
using a small local `_make_comment(body: str) -> CommentData` helper (mirror `_make_issue`'s
style already in that file). Cover:

- empty `comments` list → `None`
- single comment, marker in first line of a multi-line body → full body returned
- marker inside a heading (`"## ❌ Implementation Failed"`) → matches (substring, not prefix)
- comment with empty `body` (`""`) → skipped without raising
- more than `window` comments; only the most recent `window` are considered — an older
  match outside the window is not found
- two comments within the window both match → the more recent one wins
- no comment in the window matches → `None`
- custom `marker` and `window` arguments are respected

## Commit

One commit: new tests + `find_latest_marked_comment` + passing pylint/pytest/mypy.

## Prompt

> Implement step 1 of `pr_info/steps/summary.md` (GitHub issue #309) exactly as specified
> in `pr_info/steps/step_1.md`. Write the tests in
> `tests/github_operations/test_formatters.py` first, confirm they fail, then add
> `find_latest_marked_comment` to `src/mcp_workspace/github_operations/formatters.py` and
> confirm they pass. Run pylint, pytest (`-n auto`), and mypy; all must pass. Make exactly
> one commit containing tests + implementation. Do not touch any other file.
