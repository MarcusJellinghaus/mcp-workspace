# Step 4 — `github_issue_list`: make the silent truncation notice reachable

Reference: [summary.md](./summary.md)

## Context

`format_issue_list` guards its notice with `len(issues) > max_results` (line 103), but
its only production caller caps the list at `max_results` first:
`manager.py:253` breaks at `len(issues_list) >= max_results`. The condition is never
true, so **the tool truncates with no notice at all**.

There is no `total_count` equivalent for issue listing, so the tool fetches
`max_results + 1` and uses the surplus item to prove more exist. It renders `30+`,
not an exact total, because it does not have one.

The notice tail names `state/labels/assignee/since` and **must not** say "refine your
query" — `github_issue_list` has no `query` parameter, and naming one would name a
parameter the tool does not accept.

## WHERE

- `src/mcp_workspace/github_operations/formatters.py` — `format_issue_list`, lines 103-108
- `src/mcp_workspace/server.py` — `github_issue_list`, lines 646-653
- `tests/github_operations/test_formatters.py` — `test_format_issue_list_max_results_cap`
  (line 173)
- `tests/github_operations/test_github_read_tools.py` — `test_github_issue_list_with_filters`
  (line 213)

## WHAT

`format_issue_list`'s signature is **unchanged**:

```python
def format_issue_list(issues: list[IssueData], max_results: int = 30) -> str:
```

Only its notice string changes; the `len(issues) > max_results` guard stays exactly as
it is and becomes reachable once the caller over-fetches.

In `server.py`, `github_issue_list`'s own signature is also unchanged. Only the value
passed to the manager changes.

## HOW

`manager.list_issues` already accepts `max_results: Optional[int]`, so no manager change
is needed. Pass `max_results + 1` to the manager and the unmodified `max_results` to the
formatter — the formatter must not learn about the `+1`.

Add a short comment at the server call site recording *why* the `+1` is there, otherwise
it reads as an off-by-one bug.

## ALGORITHM

```
# server.py github_issue_list
# Over-fetch by one: no total count exists for issue listing, so the
# surplus item is what proves more results exist. The formatter still
# receives max_results and renders "30+".
issues = manager.list_issues(..., max_results=max_results + 1)
return format_issue_list(issues, max_results)

# formatters.format_issue_list — guard unchanged, message replaced
if len(issues) > max_results:
    lines.append(notice(max_results))
```

## DATA

Return value stays `str`. The appended notice becomes exactly:

```
\n... showing {max_results} of {max_results}+ results — raise max_results or narrow with state/labels/assignee/since.
```

Example at the default cap:

```
... showing 30 of 30+ results — raise max_results or narrow with state/labels/assignee/since.
```

No `min()` or `shown` local is needed: the notice only renders when
`len(issues) > max_results`, so the number shown is always exactly `max_results`.

## TDD — tests first

1. **`tests/github_operations/test_formatters.py::test_format_issue_list_max_results_cap`
   (line 173-182).** It passes 5 issues with `max_results=3` and asserts
   `"5 total results"` and `"Showing first 3"`. Both break. Replace with:
   ```python
   assert "showing 3 of 3+ results" in result
   assert "raise max_results" in result
   assert "state/labels/assignee/since" in result
   assert "query" not in result   # this tool has no query parameter
   ```
   Keep the existing `#0`/`#1`/`#2` present and `#3` absent assertions.

2. **`tests/github_operations/test_github_read_tools.py::test_github_issue_list_with_filters`
   (line 213-234).** It asserts `list_issues` was called with `max_results=10`. That
   becomes `max_results=11`.

3. **Add one new test** in `test_github_read_tools.py` for the acceptance criterion
   "the list notice appears when more results exist":
   ```python
   @patch("mcp_workspace.github_operations.issues.IssueManager")
   def test_github_issue_list_notice_when_more_exist(mock_manager_cls: MagicMock) -> None:
       """The surplus over-fetched item triggers the truncation notice."""
   ```
   Have the mock return `max_results + 1` issues (e.g. 4 issues with `max_results=3`) and
   assert `"showing 3 of 3+ results"` is in the output and that only 3 `#`-lines render.

4. **`test_github_issue_list_basic` (line 183) and `test_github_issue_list_empty`
   (line 202) need no change** — 2 and 0 issues against the default cap of 30 produce no
   notice.

Run pytest, confirm failures, then implement.

## CHECKS

All three MCP checks must pass, then `./tools/format_all.sh`.

## COMMIT

One commit: `Emit a truncation notice from github_issue_list by over-fetching one result`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`.
>
> Implement step 4 only. Following TDD, first update
> `tests/github_operations/test_formatters.py::test_format_issue_list_max_results_cap` and
> `tests/github_operations/test_github_read_tools.py::test_github_issue_list_with_filters`,
> and add the new `test_github_issue_list_notice_when_more_exist` test, all as described
> in the step file. Confirm they fail.
>
> Then: (a) in `src/mcp_workspace/github_operations/formatters.py`, replace the notice in
> `format_issue_list` with the exact string in the DATA section, leaving the signature and
> the `len(issues) > max_results` guard untouched; (b) in
> `src/mcp_workspace/server.py`, make `github_issue_list` pass `max_results=max_results + 1`
> to `manager.list_issues` while still passing the unmodified `max_results` to
> `format_issue_list`, with a comment explaining the `+1`.
>
> Do not name a `query` parameter in the notice — `github_issue_list` does not have one.
> Do not touch `format_search_results` or `github_search`; that is step 5.
>
> Use MCP tools per `CLAUDE.md`, run all three checks until they pass, run
> `./tools/format_all.sh`, and make exactly one commit.
