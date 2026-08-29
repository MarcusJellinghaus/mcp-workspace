# Summary — Issue #254: `github_search` invalid qualifier syntax

## Problem

`github_search` (`src/mcp_workspace/server.py`) sends invalid GitHub search
syntax. GitHub does something undefined with it and the caller gets
plausible-looking wrong answers. The failure is silent — results come back,
look reasonable, and are wrong.

Two independent causes, same failure mode:

**Cause A — auto-added `is:` qualifiers** (`server.py:772-776`, footer at
`806-807`). When the query contains no `is:` qualifier, the code appends
`is:issue is:pull-request`. Two tokens naming different result types do not OR
— the last one wins — so the tool silently returned **pull requests only**,
never issues, in its default shape. (Live probing in step 3 corrected an earlier
reading of this cause: `is:pull-request` *is* current GitHub syntax — GitHub's
own 422 message names it — so the defect is the type collision, not the
spelling.)

**Cause B — `labels` sends the wrong qualifier** (`server.py:779-784`).
`state`, `labels` and `assignee` are passed as `**qualifiers` to PyGithub's
`search_issues`, which folds each entry into the query as `f"{key}:{value}"`.
So `labels=["bug", "urgent"]` becomes `labels:bug,urgent`. GitHub's qualifier is
`label:` — singular, one occurrence per label. This is structural, not a typo:
a dict cannot emit `label:` twice, so the mechanism cannot express a correct
multi-label query. The `labels` parameter has never worked.

## Architectural / design changes

The change is small and local to one function, but it moves one responsibility
across a boundary:

1. **Query construction moves out of PyGithub and into `github_search`.**
   Previously the outgoing query string was assembled in two places: our code
   built the `repo:` prefix and free text, then PyGithub's `search_issues`
   appended `state:`/`labels:`/`assignee:` from `**kwargs`. Neither half could
   see the whole. After this change `github_search` builds the complete query
   string itself and passes it as a single `query` argument.

   This is what makes the mocked tests meaningful. With construction split, no
   test could observe the real outgoing query — which is why
   `test_github_search_qualifier_injection` asserted that
   `is:issue is:pull-request` was present and passed for months while the query
   was nonsense. With construction in one place, mocked tests assert the exact
   final string.

2. **`sort` and `order` stay as `search_issues` kwargs.** PyGithub turns those
   into real URL parameters, not query text, so they are not part of the query
   string and must not be folded into it.

3. **~~No default `is:` qualifier is added in its place.~~ Superseded by
   step 4 — the default is `is:issue`.** The original rationale was that
   `/search/issues` covers issues and PRs by default, so defaulting to
   `is:issue` would remove the only PR-discovery path. Live probes in step 3
   disproved both halves: `/search/issues` now returns HTTP 422 for any query
   naming no result type, and the old `is:issue is:pull-request` footer never
   ORed the two types — the last token won, so the tool returned **PRs only**.
   Step 4 therefore adds `is:issue` when the query names no type. PRs stay
   reachable via an inline `is:pull-request`. See [step_4.md](./step_4.md).

4. **Verification strategy changes.** A mocked test cannot prove GitHub accepts
   the syntax — that is how this bug shipped. The mocked tests now assert the
   exact query string, and one live `@pytest.mark.github_integration` test
   proves GitHub accepts and honors it.

No new modules, no new abstractions. Deliberately **no** `_build_search_query`
helper is extracted: the mock already exposes the exact string handed to
`search_issues`, so a helper would add indirection that tests nothing extra.

## Deviation from issue #254's decision table

Issue #254 records: *"Default `is:` qualifier after the fix | None."* **The
implementation does not follow that decision — it defaults to `is:issue`.**

The issue's rationale was that `/search/issues` covers issues and PRs by
default, so adding `is:issue` would remove the only PR-discovery path. Live
probes in [step_3.md](./step_3.md) disproved both halves:

- A query naming no result type now returns
  `Error: Query must include 'is:issue' or 'is:pull-request': 422`, so "no
  default" makes **every** plain `github_search` call fail.
- The old `is:issue is:pull-request` footer never ORed the two types — the last
  token won, so the tool was returning **PRs only**, never issues.

Defaulting to `is:issue` therefore flips a broken default rather than removing a
working capability. PRs stay reachable with an inline `is:pull-request`, which
the `github_search` docstring states. Recorded here so the issue's decision
table is not left silently contradicting the shipped behaviour; the issue text
itself still needs amending by the maintainer.

## Design decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Scope of the `labels` bug | Folded into this work | Same function, same root cause, adjacent lines |
| How to send qualifiers | Build the full query string in `github_search` | One place to construct, one place to assert |
| State qualifier form | `is:open`, not `state:open` | `is:open` is certain syntax; `state:open` is probable but unverified. No reason to gamble when the alternative is free |
| Default `is:` qualifier | `is:issue` when the query names no result type (step 4) | `/search/issues` returns HTTP 422 without one, so "no default" makes every plain search fail. `is:issue` flips a default that findings in step 3 show was never returning issues anyway; PRs stay reachable via an inline `is:pull-request` |
| Label quoting | Always quote: `label:"bug"` | Branch-free, and required in practice — this repo's own labels contain colons (`status-01:created`) |
| `state` vocabulary | `"open"` / `"closed"` → `is:open` / `is:closed`; `"all"` → no state token; anything else → `"Error: Invalid state: ..."` before the API call | `"all"` is `github_issue_list`'s vocabulary and callers will reach for it, and `/search/issues` already covers both states, so it maps cleanly to "no filter". Unrecognised values must fail loudly — sending them on is exactly the silent-wrong-answer failure this issue is about. Pinned by tests and the docstring |
| Live test anchor | Discovered at runtime, not hard-coded: the oldest open issue carrying a non-`status-` label | Hard-coding breaks when the issue is closed or relabeled. `status-NN:` labels are promoted by this repo's own automation and GitHub's search index lags label mutations, so anchoring on one makes the test flaky; the oldest non-`status-` label is the least likely to have moved. An empty `list_issues` result is checked against `_get_repository()` so a swallowed auth error fails rather than silently skips |
| `advanced_search=true` | Out of scope — and not reachable | PyGithub's `Github.search_issues` folds every `**qualifiers` entry into the *query text* as `f"{key}:{value}"`; only `sort` and `order` become URL parameters. Sending it would require bypassing the helper and calling the `Requester` directly |

## Files created or modified

### Modified

| File | Change | Step |
|------|--------|------|
| `src/mcp_workspace/server.py` | Remove auto-add block, footer and now-unused `import re`; update docstring | 1 |
| `src/mcp_workspace/server.py` | Build full query string for `state`/`labels`/`assignee`; validate the `state` vocabulary and document it | 2 |
| `tests/github_operations/test_github_read_tools.py` | Delete `test_github_search_qualifier_injection`; strip injection assertions | 1 |
| `tests/github_operations/test_github_read_tools.py` | Exact-query assertions for `state`/`labels`/`assignee`, the qualifier-only (`query=""`) path, and the `state` vocabulary | 2 |
| `tests/github_operations/test_github_read_tools.py` | Add live `@pytest.mark.github_integration` test | 3 |
| `src/mcp_workspace/server.py` | Add `is:issue` when the query names no result type; restore `import re`; update docstring | 4 |
| `tests/github_operations/test_github_read_tools.py` | Update exact-query assertions for the `is:issue` default; add default and suppression tests | 4 |
| `tests/LLM_Test.md` | Line 139 expects the removed `(auto-added: ...)` footer | 1 |
| `tests/LLM_Test.md` | Line 139 notes `is:issue` is the default result type | 4 |

The `github_search` tests listed above were written in
`tests/github_operations/test_github_read_tools.py` and later moved — see
"Review rework" below.

### Created

| File | Change |
|------|--------|
| `tests/github_operations/test_github_search_tool.py` | All `github_search` unit tests plus the live `github_integration` tests, split out of `test_github_read_tools.py` when it passed the 750-line limit |

No new modules or packages under `src/`.

### Review rework

Changes made in response to review rounds, after the four planned steps landed.
They are not part of any step; the reasoning is in
[../implementation_review_log_1.md](../implementation_review_log_1.md) and
[../implementation_review_log_2.md](../implementation_review_log_2.md).

| File | Change |
|------|--------|
| `tests/github_operations/test_github_search_tool.py` | Created by the file split (above); `test_github_read_tools.py` keeps the `github_issue_view` / `github_issue_list` / `github_pr_view` tests |
| `tests/github_operations/conftest.py` | `setup_server` moved here from the two test modules, which had diverging copies after the split. Kept non-autouse — `project_dir` copies test data per test — so each module opts in via `pytestmark` |
| `src/mcp_workspace/server.py` | Reject `type:pull-request` before the API call: GitHub matches nothing against it, so forwarding it returns an empty result indistinguishable from a genuine one |
| `src/mcp_workspace/server.py` | Reject a label containing a double quote: GitHub has no documented escape inside a quoted qualifier, so it cannot be expressed |
| `src/mcp_workspace/server.py` | Reject an empty or whitespace-only label: it would go out as `label:""` and match nothing, reading as a genuine empty result |
| `src/mcp_workspace/server.py` | Reject an `assignee` containing whitespace: unquoted in the query, it would split into `assignee:john` plus a stray free-text term |
| `src/mcp_workspace/server.py` | Match the `state` vocabulary case-insensitively, like every inline qualifier check |
| `src/mcp_workspace/server.py` | Docstring: only the five listed spellings suppress the `is:issue` default, so a PR search written with a PR-only qualifier (`is:merged`, `base:`, …) needs an explicit `is:pull-request`; `type:pull-request` is rejected outright and so cannot be used as free text |
| `src/mcp_workspace/server.py` | Docstring: a negated qualifier (`-is:issue`, `-is:open`) suppresses neither the `is:issue` default nor the `state` argument. Documented rather than coded for the same reason as the PR-only qualifiers — reading `-is:issue` as naming a type would leave a query naming none, which GitHub answers with a 422 |

### Explicitly unchanged

- `vulture_whitelist.py:47` and `.claude/CLAUDE.md:53` reference the tool only
  by name — no change needed.
- `Dict` stays imported in `server.py` (still used at lines 127 and 923). `re`
  becomes unused in step 1 and is restored in step 4 for the result-type check.
- `src/mcp_workspace/github_operations/formatters.py` — `format_search_results`
  is unchanged.
- `docs/ARCHITECTURE.md` — no layering or dependency-isolation change; the lazy
  import of PyGithub inside the tool body is preserved.

## Steps

| Step | Content | Commit |
|------|---------|--------|
| [step_1.md](./step_1.md) | Cause A — remove auto-added `is:` qualifiers and footer | 1 |
| [step_2.md](./step_2.md) | Cause B — build full query string for `state`/`labels`/`assignee` | 1 |
| [step_3.md](./step_3.md) | Live integration test proving GitHub accepts the syntax | 1 |
| [step_4.md](./step_4.md) | Default `is:issue` — GitHub 422s a query naming no result type | 1 |

Steps 1 and 2 touch adjacent lines in the same function but are independent
fixes with independent tests, so they are separate commits. Step 2 assumes
step 1 has landed.

## Checks

After each step, all three must pass:

```
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
mcp__mcp-tools-py__run_mypy_check
```

Step 1 additionally requires `mcp__mcp-tools-py__run_vulture_check` to confirm
the removed `import re` leaves nothing flagged.
