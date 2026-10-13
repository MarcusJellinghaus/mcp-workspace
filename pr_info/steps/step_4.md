# Step 4 — `fetch_review_data`: surface `comment_id` / `thread_id`

Read `pr_info/steps/summary.md` first for overall context. Independent of steps 2/3 —
only depends on step 1 having landed (for a clean branch history; no code dependency).

## Goal

Extend the GraphQL query `fetch_review_data` already issues so each unresolved-thread
entry carries the REST comment ID (`databaseId`) and the GraphQL thread ID (`id`) —
the IDs the two new tools from steps 2/3 need, surfaced to callers of
`get_pr_feedback()` / `/check_branch_status`.

## WHERE

- `src/mcp_workspace/github_operations/_pr_feedback_sources.py` — `fetch_review_data`
- `tests/github_operations/test_pr_manager_feedback.py` — existing GraphQL response
  fixtures and assertions

## WHAT

No function signature changes. `fetch_review_data(manager, pr_number)` still returns
`Tuple[list[dict[str, Any]], int, list[dict[str, Any]], Optional[GithubException]]`;
each dict in the first element (currently `{path, line, author, body, diff_hunk}`)
gains two keys: `comment_id` (`Optional[int]`) and `thread_id` (`Optional[str]`).

## HOW

- Add `id` to the `reviewThreads.nodes` selection (alongside the existing `isResolved`)
  and `databaseId` to the `comments.nodes` selection (alongside `author`, `body`,
  `path`, `line`, `diffHunk`).
- Populate the two new dict keys from the already-extracted `thread` and `first`
  (first comment) variables — no new traversal needed, they are already in scope at
  the point `unresolved_threads.append(...)` is called.
- Resolved threads are **not** changed — they stay count-only
  (`resolved_count += 1; continue`), per the issue's scoping of ID rendering to
  unresolved threads.

## ALGORITHM

```
# GraphQL query gains:
#   reviewThreads.nodes { id isResolved comments.nodes { ... databaseId } }

for thread in thread_nodes:
    if thread is None: continue
    if thread.get("isResolved"):
        resolved_count += 1; continue
    comment_nodes = ...
    first = next((c for c in comment_nodes if c is not None), None)
    if first is None: continue
    unresolved_threads.append({
        "path": ..., "line": ..., "author": ..., "body": ..., "diff_hunk": ...,
        "comment_id": first.get("databaseId"),
        "thread_id": thread.get("id"),
    })
```

## DATA

`unresolved_threads` entry shape (all still `dict[str, Any]`, no TypedDict — matches
existing untyped convention in this module):

```python
{
    "path": str, "line": Optional[int], "author": str, "body": str,
    "diff_hunk": str, "comment_id": Optional[int], "thread_id": Optional[str],
}
```

## Tests (write first)

Update `tests/github_operations/test_pr_manager_feedback.py`'s GraphQL response
fixtures (the ones feeding `fetch_review_data`'s mocked `requestJsonAndCheck`) to
include `databaseId` on comment nodes and `id` on thread nodes, then assert the
returned `unresolved_threads` entries contain the matching `comment_id`/`thread_id`
values. Also add one case where a thread node omits `databaseId`/`id` (e.g. a
permission-limited response) and assert the entry falls back to `None` for those keys
rather than raising.

## Commit

One commit: the fixture/assertion updates plus the query/extraction change. Run
pylint, pytest (`-n auto`), mypy — all must pass.

Commit message: `feat(github_operations): surface comment_id/thread_id in fetch_review_data`

## LLM prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`. Implement step 4
> only: extend `fetch_review_data`'s GraphQL query and its `unresolved_threads`
> construction in `_pr_feedback_sources.py`, following the WHERE/WHAT/HOW/ALGORITHM/
> DATA in step_4.md exactly. Update
> `tests/github_operations/test_pr_manager_feedback.py`'s fixtures and assertions
> first, then the implementation. Run pylint, pytest (`-n auto`), and mypy; all must
> pass. Make exactly one commit for this step. Do not touch `format_pr_feedback`
> (that is step 5).
