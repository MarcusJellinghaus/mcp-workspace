# Step 2 — Build the full query string for `state` / `labels` / `assignee` (Cause B)

**Context:** [summary.md](./summary.md) — Cause B. Assumes step 1 has landed.

**Goal:** `github_search` builds the complete GitHub search query itself instead
of relying on PyGithub's `**qualifiers` folding, so `labels` emits `label:`
once per label and `state` emits `is:open` / `is:closed`.

**One commit:** tests + implementation, all three checks passing.

---

## WHERE

| File | Change |
|------|--------|
| `tests/github_operations/test_github_read_tools.py` | Rewrite `test_github_search_with_qualifiers`, add label/state/qualifier-only cases |
| `src/mcp_workspace/server.py` | Replace the `qualifiers` dict build in `github_search`; validate `state`; update the `state` docstring line |

## WHAT

No signature change. `github_search` keeps its public signature; only the
translation from parameters to the outgoing request changes.

Parameter → query-string mapping:

| Parameter | Emits | Note |
|-----------|-------|------|
| `state="open"` / `"closed"` | `is:open` / `is:closed` | `is:`, not `state:` — certain syntax over probable |
| `state="all"` | nothing | `/search/issues` already covers both states; matches `github_issue_list`'s vocabulary |
| `state=<anything else>` | nothing — returns `"Error: Invalid state: ..."` | Rejected before the API call; a typo must fail loudly, not silently |
| `labels=["bug", "urgent"]` | `label:"bug" label:"urgent"` | One occurrence per label, always quoted |
| `assignee="alice"` | `assignee:alice` | |
| `query=""` | nothing | Qualifier-only search; the `if p` join filter keeps it from producing a double space |
| `sort`, `order` | *not* in the query | Stay as `search_issues` kwargs — PyGithub turns these into real URL parameters |

Do **not** extract a `_build_search_query` helper. The mock already exposes the
exact string handed to `search_issues`, so a helper adds indirection that tests
nothing extra.

## HOW — tests first (TDD)

1. **Rewrite `test_github_search_with_qualifiers`.** It currently asserts
   `state` arrives as a kwarg:
   ```python
   assert call_kwargs.get("state") == "open"
   ```
   That assertion must go — `state` becomes part of the query. Replace the body's
   assertions with an exact full-string check plus the surviving kwargs:
   ```python
   assert call_kwargs["query"] == (
       'repo:owner/repo bug is:open label:"bug" label:"urgent" assignee:alice'
   )
   assert "state" not in call_kwargs
   assert "labels" not in call_kwargs
   assert "assignee" not in call_kwargs
   assert call_kwargs.get("sort") == "created"
   assert call_kwargs.get("order") == "desc"
   ```

2. **Add a multi-label test** — the regression that motivated this step.
   Assert the query contains `label:"bug" label:"urgent"` and, explicitly, that
   `labels:bug,urgent` does **not** appear anywhere in it.

3. **Add a label-with-special-characters test.** This repo's own labels contain
   colons (`status-01:created`), which is why quoting is unconditional:
   ```python
   github_search(query="x", labels=["status-01:created"])
   # → 'repo:owner/repo x label:"status-01:created"'
   ```

4. **Add a state-only test** asserting `is:closed` (not `state:closed`) for
   `state="closed"`, and that an omitted `state` adds nothing.

5. **Add a qualifier-only test** covering the empty-query path — the `if p`
   filter below. `github_search(query="", state="open", labels=["bug"])` must
   send exactly:
   ```python
   assert call_kwargs["query"] == 'repo:owner/repo is:open label:"bug"'
   ```
   No double space, no trailing space. This is the shape step 3's live test
   sends, and this mocked test is what covers it in the default
   `-m "not ... github_integration ..."` run.

6. **Add state-vocabulary tests** for the values `github_issue_list` accepts but
   `github_search` does not translate 1:1:
   - `state="all"` → no state token in the query
     (`'repo:owner/repo bug'`), and `search_issues` is still called.
   - `state="bogus"` → returns `"Error: Invalid state: bogus. Expected 'open',
     'closed' or 'all'."` and `search_issues` is **not** called.

## HOW — implementation

Replace the current block in `src/mcp_workspace/server.py` (the lines that build
`full_query` and the `qualifiers` dict) with:

```python
if state and state not in ("open", "closed", "all"):
    return f"Error: Invalid state: {state}. Expected 'open', 'closed' or 'all'."
parts = [f"repo:{repo.full_name}", query]
if state in ("open", "closed"):
    parts.append(f"is:{state}")
for label in labels or []:
    parts.append(f'label:"{label}"')
if assignee:
    parts.append(f"assignee:{assignee}")
kwargs: Dict[str, str] = {"query": " ".join(p for p in parts if p)}
if sort:
    kwargs["sort"] = sort
if order:
    kwargs["order"] = order
# pylint: disable=protected-access
results = manager._github_client.search_issues(**kwargs)
```

Notes:
- The `if p` filter drops an empty `query`, so a qualifier-only search does not
  produce a double space.
- **`state` vocabulary is pinned before interpolation.** Only `"open"`,
  `"closed"` and `"all"` are accepted; anything else returns an error string
  before any API call. `"all"` emits no state token at all — `/search/issues`
  already covers both states — so the sibling `github_issue_list` vocabulary
  works here instead of producing an invalid `is:all` query. A typo like
  `"opne"` fails loudly rather than being sent to GitHub, which is the whole
  point of this issue: no more plausible-looking wrong answers.
- The validation happens inside the existing `try` block, before
  `search_issues` is called, so the return shape stays `"Error: ..."` like
  every other failure path.
- Update the `state` line of the docstring to name the accepted values:
  `state: Filter by state - "open", "closed" or "all" (default: all states)`.
- Keep the existing `# pylint: disable=protected-access` comment.

## ALGORITHM

```
reject with "Error: Invalid state: ..." if state not in (None, "open", "closed", "all")
parts = ["repo:{full_name}", query]
append "is:{state}"            if state in ("open", "closed")   # "all" adds nothing
append 'label:"{name}"'        for each label      # one per label, not comma-joined
append "assignee:{name}"       if assignee
kwargs = {"query": " ".join(non-empty parts)}
add sort / order to kwargs if set                  # URL params, never query text
call search_issues(**kwargs)
```

## DATA

- Outgoing `query` kwarg — a single space-joined string, parts always in this
  order: `repo:` scope, caller query, `is:{state}`, `label:"..."` per label,
  `assignee:`. The fixed order is what makes exact-string assertions possible.

  Example: `github_search(query="bug", state="open", labels=["bug", "urgent"], assignee="alice", sort="created", order="desc")`
  ```
  query = 'repo:owner/repo bug is:open label:"bug" label:"urgent" assignee:alice'
  sort  = "created"
  order = "desc"
  ```

- `kwargs` type: `Dict[str, str]` — `query` always present, `sort` and `order`
  present only when set. `state`, `labels` and `assignee` never appear as keys.
- Return value: unchanged.

## Definition of done

- `labels` emits one `label:"..."` per label; `labels:bug,urgent` appears nowhere.
- `state` emits `is:open` / `is:closed`; `state:` appears nowhere.
- `state="all"` emits no state token; an unrecognised `state` returns an error
  without calling `search_issues`; the docstring names the accepted values.
- A qualifier-only search (`query=""`) produces no double or trailing space, and
  a mocked test asserts that exact string.
- `sort` and `order` are still kwargs, absent from the query string.
- Mocked tests assert the exact outgoing query string.
- pylint, pytest and mypy pass.

---

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`, then implement
> step 2 only — building the full GitHub search query string inside
> `github_search` instead of passing `state`, `labels` and `assignee` through
> PyGithub's `**qualifiers` folding.
>
> Step 1 (removing the auto-added `is:` qualifiers) is already done; do not
> redo it. Keep `sort` and `order` as `search_issues` kwargs. Do not extract a
> query-building helper function — build it inline. Accept exactly `"open"`,
> `"closed"` and `"all"` for `state` — `"all"` emits no state token, anything
> else returns `"Error: Invalid state: ..."` before the API call — and say so in
> the docstring. Cover the qualifier-only path (`query=""`) with a mocked test.
>
> Follow TDD: update and add the tests in
> `tests/github_operations/test_github_read_tools.py` first, then change
> `src/mcp_workspace/server.py`.
>
> Use MCP tools for all file and check operations per `.claude/CLAUDE.md`. When
> done, run `run_pylint_check`, `run_pytest_check` (with the standard
> integration-test exclusions) and `run_mypy_check`, and fix anything they
> report. This step is one commit.
