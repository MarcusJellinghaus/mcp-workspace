# Step 5 — `github_search`: emit a notice with the exact total from `totalCount`

Reference: [summary.md](./summary.md)

## Context

`format_search_results` guards its notice with `len(items) > max_results` (line 189), but
`server.py:793` breaks the collection loop at `i >= max_results`, so the condition is
never true and **the tool truncates with no notice at all**.

Unlike `github_issue_list`, search *can* state an exact total. GitHub's search endpoint
returns `total_count` in the first page response and PyGithub exposes it as
`PaginatedList.totalCount` without an extra request. The `+1` over-fetch used in step 4
would cost search a real extra API call — GitHub pages search at 30 and `max_results`
defaults to 30, so item 31 always falls on the next page, one extra request per
default-sized search against a 30 requests/minute search rate limit.

The notice tail says "refine your query" here, which is good advice: `github_search`
exposes `query` (with inline GitHub qualifiers) alongside `state`, `labels`, `assignee`,
`sort` and `order`, and with `sort`/`order` set the capped results are the *top* N by the
chosen ordering.

## WHERE

- `src/mcp_workspace/github_operations/formatters.py` — `format_search_results`, lines 164-196
- `src/mcp_workspace/server.py` — `github_search`, lines 790-805
- `tests/github_operations/test_formatters.py` — `test_format_search_results_max_results_cap`
  (line 352)
- `tests/github_operations/test_github_read_tools.py` — new test

## WHAT

`format_search_results` gains one optional keyword argument:

```python
def format_search_results(
    items: list[dict[str, Any]],
    max_results: int = 30,
    total_count: Optional[int] = None,
) -> str:
```

`Optional` is already imported at line 7. Document `total_count` in the docstring as
"exact total from the search API when known; falls back to `len(items)`".

## HOW

In `server.py`, read `totalCount` **after** the collection loop, not before. PyGithub
populates `total_count` from the already-fetched first search page, so reading it after
iteration is free; reading it before any page is fetched triggers a separate
`per_page=1` request — exactly the extra call this design exists to avoid. Put that
reasoning in a comment.

Use `getattr(results, "totalCount", None)` rather than a direct attribute access. The
existing tests mock `search_issues` with a plain `list`, which has no `totalCount`, and
the `None` fallback keeps them working without rewriting each mock.

## ALGORITHM

```
# server.py github_search, after the existing `for i, item in enumerate(results)` loop
# Read totalCount only after iterating: PyGithub fills it from the first
# search page we already fetched. Reading it earlier costs an extra request.
total_count: Optional[int] = getattr(results, "totalCount", None)
result = format_search_results(items, max_results, total_count)

# formatters.format_search_results, replacing the guard at lines 189-194
shown = len(lines)                                        # exactly min(len(items), max_results)
total = total_count if total_count is not None else len(items)
if total > shown:
    lines.append(notice(shown, total))
```

The single `total > shown` comparison replaces the old `len(items) > max_results` guard
and covers both the production path (exact `totalCount`) and any caller that passes more
items than `max_results`. No `min()` is needed — `lines` was built from
`items[:max_results]`, so `len(lines)` is already the number actually shown.

## DATA

Return value stays `str`. The appended notice becomes exactly:

```
\n... showing {shown} of {total} results — raise max_results or refine your query.
```

Example:

```
... showing 30 of 412 results — raise max_results or refine your query.
```

`total_count` is `Optional[int]`; when `None`, `total` falls back to `len(items)`.

The existing `(auto-added: is:issue is:pull-request)` suffix appended at
`server.py:806-807` is untouched and still lands after the notice.

## TDD — tests first

1. **`tests/github_operations/test_formatters.py::test_format_search_results_max_results_cap`
   (line 352-364).** It passes 5 items with `max_results=3` and no `total_count`, and
   asserts `"5 total results"` / `"Showing first 3"`. Both break. Replace with:
   ```python
   assert "showing 3 of 5 results" in result
   assert "raise max_results" in result
   assert "refine your query" in result
   ```
   Keep the `#0`/`#1`/`#2` present and `#3` absent assertions.

2. **Add a formatter test for the exact-total path:**
   ```python
   def test_format_search_results_uses_total_count(self) -> None:
       """An explicit total_count is rendered instead of len(items)."""
   ```
   Pass 3 items with `max_results=3, total_count=412` and assert
   `"showing 3 of 412 results" in result`.

3. **Add a server-level test** in `tests/github_operations/test_github_read_tools.py` for
   the acceptance criterion "`github_search` states the exact total":
   ```python
   @patch("mcp_workspace.github_operations.issues.IssueManager")
   def test_github_search_notice_states_exact_total(mock_manager_cls: MagicMock) -> None:
       """The notice reports PaginatedList.totalCount, not the item count."""
   ```
   Model it on `test_github_search_max_results_cap` (line 523-551), but make
   `search_issues` return an iterable that carries `totalCount`. A `MagicMock` with
   `__iter__` configured is the simplest option that avoids pylint naming complaints on a
   camelCase attribute:
   ```python
   results = MagicMock()
   results.__iter__.return_value = iter(items)
   results.totalCount = 412
   mock_mgr._github_client.search_issues.return_value = results
   ```
   Call `github_search(query="test", max_results=3)` and assert
   `"showing 3 of 412 results"` is in the output.

4. **`test_github_search_max_results_cap` (line 523) needs no change.** It returns a plain
   list of 10 items with `max_results=3`; `getattr` yields `None`, `total` falls back to
   10, and its assertions only count `#`-prefixed lines, of which there are still 3.
   `test_github_search_basic`, `_empty`, `_with_qualifiers` and
   `_issue_vs_pr_indicator` are likewise unaffected.

Run pytest, confirm failures, then implement.

## CHECKS

All three MCP checks must pass, then `./tools/format_all.sh`. Mypy is strict, so annotate
the `getattr` result as `Optional[int]` at the call site.

## COMMIT

One commit: `Emit a truncation notice from github_search using the exact search totalCount`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`.
>
> Implement step 5 only. Following TDD, first update
> `tests/github_operations/test_formatters.py::test_format_search_results_max_results_cap`,
> add `test_format_search_results_uses_total_count`, and add
> `test_github_search_notice_states_exact_total` to
> `tests/github_operations/test_github_read_tools.py`, all as described in the step file.
> Confirm they fail.
>
> Then: (a) in `src/mcp_workspace/github_operations/formatters.py`, add the
> `total_count: Optional[int] = None` parameter to `format_search_results`, document it,
> and replace the notice guard with the single `total > shown` comparison and the exact
> message in the DATA section; (b) in `src/mcp_workspace/server.py`, in `github_search`,
> read `total_count: Optional[int] = getattr(results, "totalCount", None)` **after** the
> collection loop with a comment explaining the ordering, and pass it to
> `format_search_results`.
>
> Do not over-fetch by one here — the step file explains why search uses `totalCount`
> instead. Do not touch `format_issue_list` or `github_issue_list`; that is step 4.
>
> Use MCP tools per `CLAUDE.md`, run all three checks until they pass, run
> `./tools/format_all.sh`, and make exactly one commit.
