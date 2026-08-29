# Step 4 — Default to `is:issue` (unblocks step 3's live run)

**Context:** [summary.md](./summary.md), and the "Live-run result" and
"Follow-up findings" sections of [step_3.md](./step_3.md).

**Goal:** `github_search` never sends a query that GitHub rejects. When the
caller names no result type, `is:issue` is added.

**One commit:** tests + implementation + docs.

---

## Why

Step 1 removed the auto-added `is:issue is:pull-request` footer, on the
summary's decision #3 that `/search/issues` "already covers issues and PRs by
default". Step 3's live run disproved that: every query naming no result type
now returns

```
Error: Query must include 'is:issue' or 'is:pull-request': 422
```

so after step 1 **every** `github_search` call failed unless the caller happened
to include an `is:` token inline.

Three findings from step 3's live probes set the fix:

1. `is:pull-request` *is* current GitHub syntax — GitHub's own 422 message names
   it. The summary's original claim that the qualifier is only `is:pr` was
   wrong.
2. `is:issue is:pull-request` does not OR; the last token wins. Probing the
   pre-step-1 server with `query="search"` returned 16 results, **all PRs**,
   in a repo with matching open issues. So the old default returned PRs only —
   defaulting to `is:issue` flips a broken default rather than removing a
   working capability, and decision #3's rationale does not hold.
3. `advanced_search=true` is not reachable through PyGithub's `search_issues`:
   it folds every `**qualifiers` entry into the *query text* as
   `f"{key}:{value}"` (`github/MainClass.py`), so passing it would append the
   literal text `advanced_search:True`. Only `sort` and `order` become URL
   parameters.

That leaves defaulting to `is:issue`, with PRs reachable via an inline
`is:pull-request`. This reverses summary decision #3, which is amended
accordingly.

## WHERE

| File | Change |
|------|--------|
| `src/mcp_workspace/server.py` | Restore `import re`; add the default; update the docstring |
| `tests/github_operations/test_github_read_tools.py` | Update exact-query assertions; add two parametrized tests |
| `tests/LLM_Test.md` | Line 139 — note the default result type |
| `pr_info/steps/summary.md` | Amend Cause A, decision #3, the decision table and the file table |

## WHAT

No signature change. `github_search` keeps its exact public signature; only the
outgoing query string changes.

## HOW — implementation

In `github_search`, between the repo scope and the caller's query:

```python
parts = [f"repo:{repo.full_name}"]
# GitHub's /search/issues rejects a query that names no result type
if not re.search(
    r"(?:^|\s)is:(?:issue|pr|pull-request)(?![\w-])", query, re.IGNORECASE
):
    parts.append("is:issue")
parts.append(query)
```

- The token goes **after the repo scope and before the caller's text**, so the
  two scope-like qualifiers sit together and the caller's free text stays
  contiguous.
- The pattern accepts all three spellings — `is:issue`, `is:pr`,
  `is:pull-request`. `is:pr` is included deliberately: if a caller states a PR
  intent in that spelling, silently appending `is:issue` would override it and
  (per finding 2) win, which is exactly this issue's silent-wrong-answer failure
  mode. If GitHub does not accept `is:pr`, the caller gets GitHub's own explicit
  422 naming the two forms it wants — an honest error beats a wrong answer.
- `(?![\w-])` prevents matching `is:issuebug` or `is:pull-requests`.
- `(?:^|\s)` prevents matching `release:issue` or `this:pr`.
- `re.IGNORECASE` matches the case-insensitivity of the block step 1 removed.

`import re` returns to `server.py`; step 1 removed it as the last `re.` usage.

## HOW — tests

The default changes the outgoing string for every mocked test that asserts it,
so six existing exact-string assertions gain `is:issue` after the repo scope:
`test_github_search_basic`, `test_github_search_with_qualifiers`,
`test_github_search_multiple_labels`,
`test_github_search_label_with_special_characters`,
`test_github_search_state_emits_is_qualifier` (both calls),
`test_github_search_qualifiers_only` and
`test_github_search_state_all_emits_no_token`.

`test_github_search_sends_query_unmodified` already passes
`query="Jenkins is:issue"`, so its expected string is unchanged — its meaning
becomes "an explicit type token suppresses the default", and its docstring says
so.

Two new parametrized tests:

- `test_github_search_explicit_type_suppresses_default` — `is:pull-request`,
  `is:pr`, `IS:PULL-REQUEST` and a bare `is:pull-request` all leave the query
  untouched.
- `test_github_search_defaults_to_is_issue` — `bug`, `""`, `is:issuebug`,
  `is:pull-requests`, `release:issue` and `this:pr` all get `is:issue` added.
  The near-miss cases pin the two regex boundaries.

## ALGORITHM

```
build ["repo:{full_name}"]
if query names no result type: append "is:issue"
append query
append is:{state} / label:"..." / assignee:... as before   # steps 1-2, unchanged
join non-empty parts with a space -> query kwarg
```

## DATA

Outgoing `query` kwarg, by example:

| Call | Query sent |
|------|-----------|
| `github_search("fix")` | `repo:owner/repo is:issue fix` |
| `github_search("", state="open", labels=["bug"])` | `repo:owner/repo is:issue is:open label:"bug"` |
| `github_search("fix is:pull-request")` | `repo:owner/repo fix is:pull-request` |

Return value shape is unchanged.

## Definition of done

- No `github_search` call can reach GitHub without a result-type token.
- An inline `is:issue`, `is:pr` or `is:pull-request` suppresses the default.
- Docstring states the default and how to search PRs.
- `summary.md` decision #3 is amended, not silently contradicted.
- pylint, pytest and mypy pass, **and** step 3's live test passes:
  `run_pytest_check(extra_args=["-n", "auto"], markers=["github_integration"])`.

## Result

All four checks pass: pylint clean, mypy clean, 1577 unit tests pass
(1567 before, plus the 10 new parametrized cases), and the live
`github_integration` run is 15 passed / 1 skipped — including
`test_github_search_live_label_and_state_filters`, which had been failing with
the 422 since step 3 landed.

## Open point for the maintainer — resolved

This step reverses an explicitly recorded design decision (summary #3) and
changes `github_search`'s public default from "issues and PRs" (which findings 1
and 2 show was really "PRs only") to "issues". It was implemented on the
recommendation recorded twice in step_3.md rather than on an explicit
instruction, because step 3 could not otherwise be completed. The alternative
resolution — require callers to pass a type token and error otherwise — would
have been a small, self-contained revert.

**Decision: keep the `is:issue` default as implemented.** The two options were
weighed as follows:

- *Default to `is:issue`* (implemented). Every existing call site keeps working.
  The default result type changes from "PRs only" — which was never the intent
  and was never documented — to "issues", which is what the tool's name and
  docstring have always promised. PRs stay reachable with an inline
  `is:pull-request`, documented in the docstring.
- *Require an explicit type token.* Every existing caller breaks with an error,
  in exchange for making the choice explicit. That trades a working default for
  a deferred decision at every call site, and the caller has no better
  information than the tool does.

Since no caller ever asked for PR-only results and the observed behaviour was a
bug rather than a capability, flipping the default is not a capability
regression. Decision #3 in [summary.md](./summary.md) is amended (not silently
contradicted) and the reversal is stated in the docstring, so the change is
discoverable by anyone who relied on the old shape.

Re-verified at review time on the current tree: pylint clean, mypy clean,
1577 unit tests pass (1 skipped).
