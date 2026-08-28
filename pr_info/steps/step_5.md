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

**The current loop already pays that request.** `for i, item in enumerate(results): if i
>= max_results: break` (`server.py:792-794`) pulls item index `max_results` *before* the
guard runs, and pulling item 31 out of a `PaginatedList` fetches page 2. So the extra
call this design exists to avoid is being made today, on every default-sized search, for
an item that is immediately discarded. Since the loop is being touched anyway, stop
before the surplus item: `itertools.islice(results, max_results)` yields at most
`max_results` items and never calls `next()` again, so page 2 is not fetched.

**One behavioural difference has to be closed: negative `max_results`.** `max_results` is
an unvalidated tool parameter. The current `enumerate` guard breaks on the first
iteration for any negative value and returns `No results found.`, but `islice` rejects a
negative stop with `ValueError: Stop argument for islice() must be None or an integer:
0 <= x <= sys.maxsize`, which the tool's `except Exception` would turn into
`Error: Stop argument for islice()...`. Clamp with `max(0, max_results)` at the `islice`
call so the swap is behaviour-preserving. `max_results=0` needs no clamp and is already
identical (`islice` yields nothing, as the current guard does); with the clamp, a
negative value likewise collects no items and `format_search_results` returns
`No results found.` from its empty-list early return, exactly as today.

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

In `server.py`, replace `enumerate(results)` + the `i >= max_results` guard with
`islice(results, max(0, max_results))` (`from itertools import islice` at module level —
stdlib, so no lazy-import concern). The loop body is unchanged apart from losing the
guard. The `max(0, ...)` keeps a negative `max_results` returning `No results found.`
instead of raising inside `islice`; leave the value passed to `format_search_results`
unclamped so the formatter's signature and defaults are untouched.

Read `totalCount` **after** the collection loop, not before. PyGithub populates
`total_count` from the already-fetched first search page, so reading it after iteration is
free; reading it before any page is fetched triggers a separate `per_page=1` request —
exactly the extra call this design exists to avoid. Put that reasoning in a comment.

Use `getattr(results, "totalCount", None)` rather than a direct attribute access. The
existing tests mock `search_issues` with a plain `list`, which has no `totalCount`, and
the `None` fallback keeps them working without rewriting each mock.

## ALGORITHM

```
# server.py github_search
# islice stops at max_results without pulling the next item, so a
# default-sized search never fetches page 2 just to discard item 31.
# max(0, ...) because islice rejects a negative stop, where the old
# enumerate guard simply collected nothing.
for item in islice(results, max(0, max_results)):
    ...                                                   # body unchanged

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

4. **Add a guard test for a non-positive cap**, since `islice` would otherwise raise
   where the old loop did not:
   ```python
   @pytest.mark.parametrize("max_results", [0, -1])
   @patch("mcp_workspace.github_operations.issues.IssueManager")
   def test_github_search_non_positive_max_results(
       mock_manager_cls: MagicMock, max_results: int
   ) -> None:
       """A zero or negative cap collects nothing instead of erroring."""
   ```
   Return a plain list of items from `search_issues` and assert the result contains
   `"No results found."` and does **not** start with `"Error:"`.

5. **`test_github_search_max_results_cap` (line 523) needs no change.** It returns a plain
   list of 10 items with `max_results=3`; `islice` still yields 3, `getattr` yields
   `None`, and `total` falls back to `len(items)` — which is 3, not 10, because the
   formatter only ever receives the capped list. So no notice renders and its assertion
   that exactly 3 `#`-prefixed lines appear still holds. (This is why the notice on the
   production path depends on `totalCount`: with `total_count=None` the server-side call
   can never report more than it shows.) `test_github_search_basic`, `_empty`,
   `_with_qualifiers` and `_issue_vs_pr_indicator` are likewise unaffected.

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
> `test_github_search_notice_states_exact_total` and
> `test_github_search_non_positive_max_results` to
> `tests/github_operations/test_github_read_tools.py`, all as described in the step file.
> Confirm they fail.
>
> Then: (a) in `src/mcp_workspace/github_operations/formatters.py`, add the
> `total_count: Optional[int] = None` parameter to `format_search_results`, document it,
> and replace the notice guard with the single `total > shown` comparison and the exact
> message in the DATA section; (b) in `src/mcp_workspace/server.py`, in `github_search`,
> replace `enumerate(results)` and its `i >= max_results` guard with
> `islice(results, max(0, max_results))` (comments: stopping before the surplus item keeps
> a default-sized search on one page, and `max(0, ...)` because `islice` raises on a
> negative stop where the old guard collected nothing), then read
> `total_count: Optional[int] = getattr(results, "totalCount", None)` **after** the
> collection loop with a comment explaining the ordering, and pass it to
> `format_search_results`.
>
> Do not over-fetch by one here — the step file explains why search uses `totalCount`
> instead. Do not touch `format_issue_list` or `github_issue_list`; that is step 4.
>
> Use MCP tools per `CLAUDE.md`, run all three checks until they pass, run
> `./tools/format_all.sh`, and make exactly one commit.
