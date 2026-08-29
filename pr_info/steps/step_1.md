# Step 1 — Remove auto-added `is:` qualifiers (Cause A)

**Context:** [summary.md](./summary.md) — Cause A.

**Goal:** `github_search` sends the caller's query unmodified. No `is:` tokens
are injected, and no `(auto-added: ...)` footer is appended to the output.

**One commit:** tests + implementation + docs, all three checks passing.

---

## WHERE

| File | Change |
|------|--------|
| `tests/github_operations/test_github_read_tools.py` | Delete one test, strip assertions from three |
| `src/mcp_workspace/server.py` | Remove auto-add block, footer, `import re`; update docstring |
| `tests/LLM_Test.md` | Line 139 — drop the footer expectation |

## WHAT

No signature changes. `github_search` keeps its exact public signature:

```python
def github_search(
    query: str,
    state: Optional[str] = None,
    labels: Optional[List[str]] = None,
    assignee: Optional[str] = None,
    sort: Optional[str] = None,
    order: Optional[str] = None,
    max_results: int = 30,
) -> str:
```

This step changes only what is *appended* to `query` and to the result. Query
construction for `state`/`labels`/`assignee` is **out of scope here** — that is
step 2. Leave the `qualifiers` dict alone.

## HOW — tests first (TDD)

Write the test changes before touching `server.py`; they should fail (or in the
delete case, stop existing) against the current implementation.

1. **Delete `test_github_search_qualifier_injection`** entirely, including its
   `@pytest.mark.parametrize` block (currently lines 577-621). It tests the
   removed behaviour. `pytest` stays imported — the module-level
   `@pytest.fixture` at line 21 still uses it.

2. **`test_github_search_basic`** — remove these two assertions:
   ```python
   assert "(auto-added: is:issue is:pull-request)" in result
   assert "is:issue is:pull-request" in call_args[1]["query"]
   ```
   Replace the surviving `assert "repo:owner/repo" in call_args[1]["query"]`
   with an exact-string assertion:
   ```python
   assert call_args[1]["query"] == "repo:owner/repo fix"
   ```

3. **`test_github_search_empty`** — remove:
   ```python
   assert "(auto-added: is:issue is:pull-request)" in result
   ```

4. **`test_github_search_with_qualifiers`** — remove only:
   ```python
   assert "is:issue is:pull-request" in call_kwargs["query"]
   ```
   Leave the rest of this test as-is; step 2 rewrites it.

5. **Add a test** proving an explicit qualifier passes through untouched and
   nothing is appended:
   ```python
   @patch("mcp_workspace.github_operations.issues.IssueManager")
   def test_github_search_sends_query_unmodified(mock_manager_cls: MagicMock) -> None:
       """No is: qualifiers are added; the caller's query is sent verbatim."""
   ```
   Assert `call_kwargs["query"] == "repo:owner/repo Jenkins is:issue"` for
   `github_search(query="Jenkins is:issue")`, and that `"auto-added"` is not in
   the returned string.

**Leave `test_github_search_issue_vs_pr_indicator` alone.** Its
`startswith("(")` line filter is not dead code — `format_search_results` still
emits a trailing `(... more)` line when results are truncated.

## HOW — implementation

In `src/mcp_workspace/server.py`:

1. Delete the auto-add block (currently lines 772-776):
   ```python
   has_qualifier = re.search(
       r"(?:^|\s)is:(issue|pull-request)", query, re.IGNORECASE
   )
   if not has_qualifier:
       query = query + " is:issue is:pull-request"
   ```

2. Delete the footer (currently lines 805-808), collapsing to a direct return:
   ```python
   return format_search_results(items, max_results)
   ```

3. Delete `import re` (line 5). It is the only `re.` usage in the file —
   verify with vulture. Keep `Dict` (used at lines 127 and 923).

4. Update the docstring. Replace the second paragraph:
   ```
   Automatically scoped to current repository. Additional qualifiers
   can be included inline in the query string (e.g., "fix login author:marcus").
   ```
   with wording that states no qualifiers are added automatically, that both
   issues and PRs are returned by default, and that callers narrow the search
   themselves with `is:issue` or `is:pr` inline in `query`.

## ALGORITHM

```
build "repo:{full_name} {query}"          # query used verbatim, nothing appended
pass it plus state/labels/assignee/sort/order to search_issues   # unchanged, step 2
iterate results up to max_results, collecting number/title/state/labels/pull_request
return format_search_results(items, max_results)                 # no footer
```

## DATA

- Outgoing `query` kwarg: `"repo:owner/repo <caller query>"` — the caller's
  string with a repo scope prefix and nothing else.
- Return value: unchanged shape — `format_search_results` output, i.e. lines of
  `#N [Issue|PR] [state] Title  label1, label2`, or `"No results found."`, or
  `"Error: {e}"`. The only difference is the absence of the trailing
  `(auto-added: is:issue is:pull-request)` line.

## Docs

`tests/LLM_Test.md:139` currently reads:

```
2. `github_search(query="bug", max_results=3)` — expect results plus auto-filter note `"(auto-added: is:issue is:pull-request)"`
```

Change it to expect results only, with no footer.

## Definition of done

- `test_github_search_qualifier_injection` no longer exists.
- Mocked tests assert exact outgoing query strings.
- No `re` import, no `has_qualifier`, no footer in `server.py`.
- `tests/LLM_Test.md:139` updated.
- pylint, pytest and mypy pass; vulture reports nothing new.

---

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`, then implement
> step 1 only — removing the auto-added `is:issue is:pull-request` qualifiers
> and the `(auto-added: ...)` footer from `github_search`.
>
> Do **not** change how `state`, `labels` or `assignee` are passed to
> `search_issues` — that is step 2. Leave the `qualifiers` dict as it is.
>
> Follow TDD: change the tests in
> `tests/github_operations/test_github_read_tools.py` first, then
> `src/mcp_workspace/server.py`, then `tests/LLM_Test.md:139`.
>
> Use MCP tools for all file and check operations per `.claude/CLAUDE.md`. When
> done, run `run_pylint_check`, `run_pytest_check` (with the standard
> integration-test exclusions) and `run_mypy_check`, plus `run_vulture_check` to
> confirm the removed `import re` leaves nothing flagged. Fix anything they
> report. This step is one commit.
