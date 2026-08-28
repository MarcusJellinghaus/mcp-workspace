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
passed to the manager and the formatter changes.

## HOW

`manager.list_issues` already accepts `max_results: Optional[int]`, so no manager change
is needed. Pass `capped + 1` to the manager and `capped` to the formatter — the formatter
must not learn about the `+1`.

**Clamp `max_results` with `max(0, max_results)` first.** `max_results` is an unvalidated
tool parameter, exactly like `max_log_lines` in step 3 and `max_results` in step 5, and
both of those clamp it. Without a clamp here every negative value produces a false
notice: at `max_results=-1` the manager's `max_results is not None and len(issues_list)
>= max_results` break (`manager.py:253`) fires after the first item, the formatter slices
`issues[:-1]` to the empty list, the `len(issues) > max_results` guard is still true, and
the output is the notice alone reading `... showing -1 of -1+ results` — a negative count
over an empty list. Clamping makes the same call render `... showing 0 of 0+ results`,
which is honest: nothing was shown and more exist.

The clamp is a no-op for every sane value, including the default 30.

Add a short comment at the server call site recording *why* the `+1` is there, otherwise
it reads as an off-by-one bug, and why the clamp is there.

## ALGORITHM

```
# server.py github_issue_list
# max_results is an unvalidated tool parameter; clamp before deriving
# anything from it so a negative value cannot reach the notice as a
# negative "shown" count. Mirrors step 3's max(0, max_lines) and
# step 5's max(0, max_results) guards.
capped = max(0, max_results)
# Over-fetch by one: no total count exists for issue listing, so the
# surplus item is what proves more results exist. The formatter still
# receives the capped value and renders "30+".
issues = manager.list_issues(..., max_results=capped + 1)
return format_issue_list(issues, capped)

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

At the clamped degenerate cap the notice reads:

```
... showing 0 of 0+ results — raise max_results or narrow with state/labels/assignee/since.
```

which is honest — no issues were listed and at least one more exists — and never reports
a negative count.

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

4. **Add one parameterized test for a non-positive cap**, since `max_results` is an
   unvalidated tool parameter and this is where the clamp is proved:
   ```python
   @pytest.mark.parametrize("max_results", [0, -1])
   @patch("mcp_workspace.github_operations.issues.IssueManager")
   def test_github_issue_list_non_positive_max_results(
       mock_manager_cls: MagicMock, max_results: int
   ) -> None:
       """A zero or negative cap lists nothing and never reports a negative count."""
   ```
   Have the mock `list_issues` return 1 issue (what the manager really returns for a cap
   of 0 or 1, per its `len(issues_list) >= max_results` break). Assert:

   - `list_issues` was called with `max_results=1` — the clamped `0` plus the over-fetch;
   - `"showing 0 of 0+ results"` is in the output;
   - `"-1"` is **not** in the output and no line starts with `"#"`;
   - the result does not start with `"Error:"`.

   Both cases must produce byte-identical output, which is the point of the clamp.
   Without it the `-1` case renders `... showing -1 of -1+ results`.

5. **`test_github_issue_list_basic` (line 183) and `test_github_issue_list_empty`
   (line 202) need no change** — 2 and 0 issues against the default cap of 30 produce no
   notice. Note that both now assert against `list_issues(max_results=31)` if they assert
   on the call at all; they do not, so they stay untouched.

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
> and add the new `test_github_issue_list_notice_when_more_exist` and the parameterized
> `test_github_issue_list_non_positive_max_results` tests, all as described in the step
> file. Confirm they fail.
>
> Then: (a) in `src/mcp_workspace/github_operations/formatters.py`, replace the notice in
> `format_issue_list` with the exact string in the DATA section, leaving the signature and
> the `len(issues) > max_results` guard untouched; (b) in
> `src/mcp_workspace/server.py`, make `github_issue_list` clamp with
> `capped = max(0, max_results)`, pass `max_results=capped + 1` to `manager.list_issues`
> and `capped` to `format_issue_list`, with comments explaining both the clamp and the
> `+1`. Without the clamp a negative `max_results` renders
> `... showing -1 of -1+ results` over an empty list.
>
> Do not name a `query` parameter in the notice — `github_issue_list` does not have one.
> Do not touch `format_search_results` or `github_search`; that is step 5.
>
> Use MCP tools per `CLAUDE.md`, run all three checks until they pass, run
> `./tools/format_all.sh`, and make exactly one commit.
