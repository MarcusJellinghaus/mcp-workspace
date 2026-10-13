# Step 5 — `format_pr_feedback`: render `comment_id` / `thread_id`

Read `pr_info/steps/summary.md` first for overall context. Depends on step 4 (the
fields this step renders must already be produced by `fetch_review_data`).

## Goal

Render the `comment_id`/`thread_id` fields step 4 added, in `format_pr_feedback`'s
`[unresolved thread]` lines, so `/check_branch_status` output lets a session act on a
specific thread/comment without a separate lookup call.

## WHERE

- `src/mcp_workspace/checks/pr_feedback.py` — `format_pr_feedback`
- `tests/checks/test_branch_status_pr_feedback.py` — existing rendering assertions

## WHAT

No signature change: `format_pr_feedback(feedback: PRFeedback) -> str`. Only the
`[unresolved thread]` line's content changes.

## HOW

- Read `comment_id`/`thread_id` from each `thread` dict with `.get(..., "")` — same
  defensive style already used for `path`/`line`/`author`/`body` in this function —
  so a dict lacking these keys (e.g. an older cached response, or a direct unit-test
  fixture that doesn't set them) renders without a `KeyError`.
- Append them as a bracketed suffix on the existing `[unresolved thread] <location>
  (<author>):` line, after the author, before the colon. Omit the suffix entirely
  when both values are empty, so a thread dict without IDs renders exactly as before
  (keeps existing tests, that don't set these keys, passing unchanged where they don't
  assert on the new segment).

## ALGORITHM

```
for thread in unresolved:
    path = thread.get("path", ""); line_no = thread.get("line")
    author = thread.get("author", ""); diff_hunk = thread.get("diff_hunk", "")
    comment_id = thread.get("comment_id", ""); thread_id = thread.get("thread_id", "")
    body = _truncate_body(thread.get("body", "")); ...
    location = f"{path}:{line_no}" if line_no else path
    ids = f" [comment_id={comment_id} thread_id={thread_id}]" if (comment_id or thread_id) else ""
    rendered.append(
        f"[unresolved thread] {location} ({author}){ids}:\n"
        f"{indented_hunk}\n"
        f"  Comment: {body}"
    )
```

## DATA

No new data structures — pure rendering change on the existing `PRFeedback`/
`unresolved_threads` shape step 4 already produces.

## Tests (write first)

Update `tests/checks/test_branch_status_pr_feedback.py`:
- A thread dict including `comment_id`/`thread_id` renders the
  `[comment_id=... thread_id=...]` segment in the expected position.
- A thread dict omitting both keys (the existing fixtures already in this file)
  renders identically to before — no `[comment_id=...]` segment, no exception. Confirm
  this by running the existing tests unmodified alongside the new one.

## Commit

One commit: the test update plus the rendering change. Run pylint, pytest
(`-n auto`), mypy — all must pass.

Commit message: `feat(checks): render comment_id/thread_id in PR feedback output`

## LLM prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`. Implement step 5
> only: render `comment_id`/`thread_id` in `format_pr_feedback`'s `[unresolved
> thread]` lines in `checks/pr_feedback.py`, following the WHERE/WHAT/HOW/ALGORITHM in
> step_5.md exactly. Update `tests/checks/test_branch_status_pr_feedback.py` first,
> then the implementation, confirming the existing fixtures without these keys still
> render unchanged. Run pylint, pytest (`-n auto`), and mypy; all must pass. Make
> exactly one commit for this step. This is the final step of the issue #308
> implementation.
