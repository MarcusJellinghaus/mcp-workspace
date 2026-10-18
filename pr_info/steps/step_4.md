# Step 4 — Paginate `reviewThreads`: shared query, follow-up loop, page cap, fail-closed errors

See `pr_info/steps/summary.md` for full architecture and context. Depends on step 1 (`_request_review_page`) and step 2 (`latestOpinionatedReviews` already in the query).

## WHERE

- `src/mcp_workspace/github_operations/_pr_feedback_sources.py` — query template, `fetch_review_data` body, new `_parse_thread_nodes` helper, new `_MAX_REVIEW_THREAD_PAGES` constant.
- `tests/github_operations/test_pr_feedback_mixin.py` — new pagination tests.

## WHAT

```python
_MAX_REVIEW_THREAD_PAGES = 10

def _parse_thread_nodes(pr_data: dict[str, Any]) -> Tuple[list[dict[str, Any]], int]:
    """Parse one page's reviewThreads.nodes into (unresolved_threads, resolved_count)."""
```

(This is the existing thread-parsing loop body from `fetch_review_data`, extracted unchanged so it can run once per page instead of once total.)

## HOW

- Query template (replaces the one introduced in step 2):
  ```graphql
  query($owner: String!, $repo: String!, $prNumber: Int!, $cursor: String, $includeReviews: Boolean!) {
    repository(owner: $owner, name: $repo) {
      pullRequest(number: $prNumber) {
        reviewThreads(first: 100, after: $cursor) {
          pageInfo { hasNextPage endCursor }
          nodes { id isResolved comments(first: 5) { nodes { author { login } body path line diffHunk databaseId } } }
        }
        latestOpinionatedReviews(first: 100) @include(if: $includeReviews) {
          nodes { state author { login } body submittedAt }
        }
      }
    }
  }
  ```
  One query string, reused for every page — the `@include(if: $includeReviews)` directive is what keeps follow-up pages from refetching reviews, not a second query string.
- `fetch_review_data`'s first call: `variables = {owner, repo, prNumber, "cursor": None, "includeReviews": True}` via `_request_review_page`. `changes_requested` is parsed once from this first `pr_data` (unchanged from step 2 — never re-parsed from later pages, since `includeReviews: False` means the field is absent there).
- `unresolved_threads`/`resolved_count` now accumulate across however many pages are fetched, via `_parse_thread_nodes` called once per page.
- The follow-up loop and cap logic live directly in `fetch_review_data` (no new top-level function beyond `_parse_thread_nodes` — the loop itself is simple enough to stay inline, per KISS).

## ALGORITHM

```
headers, pr_data, error = _request_review_page(requester, query, {..., cursor: None, includeReviews: True})
if pr_data is None:
    return ([], 0, [], error)

changes_requested = _parse_changes_requested(pr_data)
threads, resolved = _parse_thread_nodes(pr_data)
page_info = (pr_data.get("reviewThreads") or {}).get("pageInfo") or {}
pages = 1

try:
    while error is None and page_info.get("hasNextPage") and pages < _MAX_REVIEW_THREAD_PAGES:
        variables = {..., "cursor": page_info.get("endCursor"), "includeReviews": False}
        headers, pr_data, error = _request_review_page(requester, query, variables)
        if pr_data is None:
            break
        more_threads, more_resolved = _parse_thread_nodes(pr_data)
        threads += more_threads
        resolved += more_resolved
        page_info = (pr_data.get("reviewThreads") or {}).get("pageInfo") or {}
        pages += 1
except GithubException as e:
    error = e

if pages >= _MAX_REVIEW_THREAD_PAGES and page_info.get("hasNextPage") and error is None:
    error = GithubException(
        200,
        {"errors": [{"message": f"reviewThreads truncated after {_MAX_REVIEW_THREAD_PAGES} pages"}]},
        headers,
    )

return (threads, resolved, changes_requested, error)
```

Notes embedded in the algorithm, not separate code paths:
- "No pagination when the first response carried errors" falls out of the `while error is None` condition — no special-case branch needed.
- Missing `pageInfo` on any page → `{}.get("hasNextPage")` is falsy → loop (or initial pagination) simply doesn't start/continue — no explicit "missing pageInfo" branch needed.
- A `GithubException` raised by `requester.requestJsonAndCheck` inside `_request_review_page` on a later page propagates out of that call; the single `try/except` around the whole loop catches it once, preserving whatever `threads`/`resolved` were accumulated before it.

## DATA

`fetch_review_data` still returns the same 4-tuple shape. `error` may now originate from any page, not just the first; `threads`/`resolved_count` reflect every page successfully parsed before the error (if any). No change to `get_pr_feedback`'s handling of the 4-tuple — it already treats a non-`None` 4th element as `unavailable["threads"]` regardless of which page produced it.

## Tests (write first)

In `tests/github_operations/test_pr_feedback_mixin.py`, using `graphql_responses=[...]` (one body per POST, already supported by `_setup_mocks`):

- Threads spanning 3 pages (`pageInfo.hasNextPage`: `True, True, False`) → all threads returned in order, `resolved_thread_count` summed across all three pages' `isResolved` nodes.
- Page 1 has no `pageInfo` key at all → treated as a single page; exactly 1 POST made.
- On the page-2 request, assert `payload["variables"]["includeReviews"] is False` and `payload["variables"]["cursor"] == <page 1's endCursor>` (inspect `requester.requestJsonAndCheck.call_args_list`).
- POST count equals `1 + number_of_follow_up_pages`, parametrized over 1 and 2 follow-up pages.
- A transient `NOT_FOUND`-then-success sequence on page 2 (reusing `_request_review_page`'s existing retry, verified in step 1) still yields that page's threads — confirms the retry helper is reused unmodified for later pages, not reimplemented.
- A page-2 request that fails permanently → `unresolved_threads` contains only page 1's threads, `result["unavailable"]["threads"]` is set, `changes_requested` from page 1 is still present (recovered data survives alongside the error).
- Parametrized cap test: page 10 has `hasNextPage: False` → no synthesized exception, all 10 pages' threads present; page 10 has `hasNextPage: True` → `unavailable["threads"]` is a `GithubException` with status 200 and message containing `"truncated after 10 pages"`.

## Commit

One commit: query/loop rewrite + `_parse_thread_nodes` + tests above.

## LLM Prompt

> Implement `pr_info/steps/step_4.md` for issue #324 (architecture in `pr_info/steps/summary.md`; depends on steps 1 and 2 already being merged). Follow TDD: write the pagination tests listed in this step first, confirm they fail against the current single-page `fetch_review_data`, then implement the shared query, `_parse_thread_nodes`, and the capped follow-up loop until green. Keep the loop inline in `fetch_review_data` — no paginator class or extra abstraction beyond `_parse_thread_nodes`. Run `mcp__mcp-tools-py__run_ruff_check`, `run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`), and `run_mypy_check` until clean, then make exactly one commit.
