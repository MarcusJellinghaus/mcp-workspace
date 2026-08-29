# Step 3 — Live integration test

**Context:** [summary.md](./summary.md). Assumes steps 1 and 2 have landed.

**Goal:** One `@pytest.mark.github_integration` test that proves GitHub accepts
and *honors* the query built in step 2 — covering the label path and the state
path against the real API, in both shapes callers use: qualifier-only
(`query=""`) and free text plus qualifiers (the issue's repro 3).

**One commit:** the test only, no production code.

---

## Why a live test

A mocked test cannot verify this fix. Every existing `github_search` test mocks
`_github_client` and asserts on the string being sent — which is exactly how the
bug shipped: `test_github_search_qualifier_injection` asserted
`is:issue is:pull-request` was present and passed for months while the query was
nonsense. The mocked tests prove we build the string we intend to build; only a
live call proves GitHub agrees.

## WHERE

| File | Change |
|------|--------|
| `tests/github_operations/test_github_read_tools.py` | Add one test at the end of the file |

## WHAT

```python
@pytest.mark.github_integration
def test_github_search_live_label_and_state_filters() -> None:
    """Live: GitHub accepts and honors label: and is:open qualifiers."""
```

Takes no fixture. Existing imports in the module cover most of it; add
`IssueManager` and `get_github_token` as function-local imports (the module
already imports `Path`, `pytest`, `github_search` and `set_project_dir`).

## HOW

**Repository under test.** Point at this repo's own checkout rather than the
`github_test_setup` fixture. That fixture clones `GITHUB_TEST_REPO_URL`, which
in CI is a sandbox repo, not `mcp_workspace`. CI's `actions/checkout` gives a
real `origin` remote, so `github_search` resolves the repo from git and
`GH_INTEGRATION_TOKEN` is already in scope for the `github-integration-tests`
job (`.github/workflows/ci.yml:228`).

```python
repo_root = Path(__file__).parents[2]
```

**Override the autouse fixture.** `setup_server` (line 21) is autouse and points
`_project_dir` at a `tmp_path` with no git remote. Call
`set_project_dir(repo_root)` inside the test to override it.

**Skip when unconfigured**, matching how `github_test_setup` behaves:

```python
if not get_github_token():
    pytest.skip("GitHub token not configured (set GITHUB_TOKEN or config file)")
```

**Guard the manager construction.** `IssueManager(project_dir=...)` raises
`ValueError` when the directory is not a git repository or has no GitHub
`origin` remote — true for source checkouts without git history and for some
local dev environments. Skip rather than error:

```python
try:
    manager = IssueManager(project_dir=repo_root)
except ValueError as exc:
    pytest.skip(f"Checkout is not a git repo with a GitHub origin: {exc}")
```

**Discover the anchor issue instead of hard-coding one.** Hard-coding an issue
number would break the day that issue is closed or relabeled. Use
`manager.list_issues(state="open")` to pick a real open, labelled issue, then
search for it.

**Pick a *stable* anchor label.** Every open issue in this repo carries a
`status-NN:` label that this repo's own automation promotes through states, and
GitHub's search index lags label mutations — a just-promoted label makes both
the anchor-number assertion and the per-line label assertion false-fail. So:

- ignore any label whose name starts with `status-`;
- walk the issue list **oldest first** (`list_issues` returns newest first, so
  iterate `reversed(issues)`) and take the first issue that still has a
  non-`status-` label. The oldest such issue is the least likely to have been
  relabeled since the search index was last updated.
- do not pass `max_results` to `list_issues` — capping it would keep only the
  newest issues, which is the opposite of what we want.

Skip if no open issue carries a non-`status-` label.

**Distinguish an empty repo from a swallowed API error.** `list_issues` is
wrapped in `@_handle_github_errors(default_return=[])`, so an auth or
permission failure returns `[]` — indistinguishable from "no open issues" and
silently skipping the only live verification this issue asks for. When the list
comes back empty, probe the repository before deciding:

```python
if not issues:
    if manager._get_repository() is None:  # pylint: disable=protected-access
        pytest.fail("GitHub API unreachable or token lacks access to this repo")
    pytest.skip("Repository has no open issues")
```

A configured token that cannot read the repo is a real failure, not a reason to
no-op.

**Assert both filters actually applied** — this is stronger than asserting one
known number, because a hard-coded number appearing in the results would not
prove the label filter took effect; unfiltered noise could contain it, which is
precisely this issue's failure mode.

- the anchor issue number is present → the `label:` filter returned it
- **every result line contains the anchor label** → the `label:` filter was
  honored as a qualifier. This is the assertion that catches the failure mode:
  if GitHub demotes `label:"..."` to free text, unrelated issues come back and
  at least one line lacks the label, so the test fails. Asserting only that the
  anchor number appears would pass on demoted free text.
- every result line shows `[open]` → the `is:open` filter took effect
- the result is not an error and not `"No results found."`

The label is part of each formatted line: `format_search_results` appends
`  label1, label2` after the title, so a plain `anchor_label in line` check per
`#` line is sufficient.

**Sort oldest-first so the anchor cannot be capped away.** The anchor is the
*oldest* matching issue, but GitHub's default ordering for `/search/issues` is
best match (effectively newest-first here), so a generous `max_results` alone
does not keep the anchor inside the result set — once the anchor label carries
more than 100 open items the oldest one falls past the cutoff and the
anchor-number assertion red-fails with no bug present. Pass
`sort="created", order="asc"` so the oldest match is returned first, and keep
`max_results=100` as headroom:

```python
result = github_search(
    query="",
    state="open",
    labels=[anchor_label],
    sort="created",
    order="asc",
    max_results=100,
)
```

`sort` and `order` are real URL parameters (step 2 keeps them as `search_issues`
kwargs), so they do not change the query string this test is verifying.

**Second live call — free text plus qualifiers (the issue's repro 3).** The
qualifier-only search above proves GitHub accepts `label:"..."` and `is:open` on
their own. The issue's repro 3 is the *combined* shape —
`github_search(query="status", state="open")` returned nothing — and that
combination is otherwise pinned only by a mocked exact-string assertion, which
by this step's own argument cannot prove GitHub honors it. So run a second live
search in the same test, with a non-empty `query`, and assert the anchor still
comes back:

```python
anchor_word = max(
    (w for w in anchor["title"].split() if w.isalpha() and len(w) >= 4),
    key=len,
    default="",
)
if not anchor_word:
    pytest.skip("Anchor issue title has no distinctive word for a free-text search")

text_result = github_search(
    query=anchor_word,
    state="open",
    labels=[anchor_label],
    sort="created",
    order="asc",
    max_results=100,
)
assert not text_result.startswith("Error:")
assert f"#{anchor['number']}" in text_result
```

`anchor_word` is the longest all-alphabetic word of at least four characters in
the anchor issue's title — deterministic, taken from a real title, and long
enough not to be dropped as a stop word. Only the anchor-number assertion is
made on this call: the per-line label and state assertions already ran on the
first call, and this call exists to prove free text and qualifiers survive
*together*. Keep the qualifier-only call as well — the two shapes verify
different things.

## ALGORITHM

```
skip if no GitHub token configured
repo_root = Path(__file__).parents[2]; set_project_dir(repo_root)
manager = IssueManager(project_dir=repo_root)      # skip on ValueError (no git repo / no GitHub origin)
issues = manager.list_issues(state="open")         # no max_results — we need the oldest, not the newest
if not issues: fail if _get_repository() is None (auth error), else skip (empty repo)
anchor = first issue in reversed(issues) with a label not starting with "status-"; skip if none
anchor_label = that label
result = github_search(query="", state="open", labels=[anchor_label],
                       sort="created", order="asc", max_results=100)   # oldest first: anchor cannot be capped away
assert anchor number in result
assert every "#" line contains "[open]" and contains the anchor label

anchor_word = longest all-alphabetic word (>= 4 chars) in the anchor title; skip if none
text_result = github_search(query=anchor_word, state="open", labels=[anchor_label],
                            sort="created", order="asc", max_results=100)   # repro 3 shape
assert text_result is not an error and anchor number in text_result
```

## DATA

- `list_issues(...)` returns `list[IssueData]`; the fields used are
  `["number"]` (int), `["title"]` (str) and `["labels"]` (list of label-name
  strings).
- `github_search(...)` returns the formatted string from
  `format_search_results`: lines of
  `#N [Issue|PR] [state] Title  label1, label2`, or `"No results found."`, or
  `"Error: {e}"`.
- Result lines are identified by `line.startswith("#")`, matching the existing
  convention in `test_github_search_max_results_cap`.

## Notes

- The anchor label is deliberately *not* a `status-NN:` label, so this test does
  not exercise colon-containing label names against the real API; the
  unconditional quoting from step 2 is still exercised (every label is quoted),
  and colon-containing names are covered by the mocked test in step 2.
- `query=""` makes this a qualifier-only search. That is valid GitHub syntax, and
  the `if p` filter added in step 2 keeps the empty string from producing a
  double space.
- The test is excluded from normal runs by the standard
  `-m "not ... github_integration ..."` exclusion, and runs in CI's dedicated
  `github-integration-tests` job.

## Definition of done

- One new test, marked `@pytest.mark.github_integration`, making two live
  searches: the qualifier-only one and the free-text-plus-qualifiers one.
- The second live search sends a non-empty `query` together with `state="open"`
  and the anchor label — the issue's repro 3 shape — and asserts the anchor
  issue number is returned and the call did not error.
- Every returned result line is asserted to carry the anchor label and `[open]`,
  not just the anchor issue number.
- The anchor is the *oldest* open issue carrying a non-`status-` label, so the
  assertions do not depend on a label this repo's automation just mutated.
- The search passes `sort="created", order="asc"`, so the oldest match is
  returned first and cannot be pushed past the `max_results=100` cap.
- Skips cleanly when no token is configured, when the checkout is not a git repo
  with a GitHub origin, and when no open issue carries a non-`status-` label.
- An empty `list_issues` result caused by an auth or permission failure **fails**
  the test instead of skipping it.
- Passes against the live API:
  `run_pytest_check(extra_args=["-n", "auto"], markers=["github_integration"])`.
- pylint, pytest and mypy pass.

---

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`, then implement
> step 3 only — adding one live `@pytest.mark.github_integration` test for
> `github_search` at the end of
> `tests/github_operations/test_github_read_tools.py`.
>
> Steps 1 and 2 are already done. This step adds **no** production code.
>
> Point the test at this repository's own checkout via
> `Path(__file__).parents[2]` and `set_project_dir`, not the
> `github_test_setup` fixture. Discover the anchor issue at runtime with
> `IssueManager.list_issues` — do not hard-code an issue number or a label, and
> pick the *oldest* open issue carrying a label that does not start with
> `status-`, so the assertions never depend on a label this repo's automation
> just promoted. Search with `sort="created", order="asc"` so that oldest anchor
> is returned first and cannot be pushed past the `max_results=100` cap by
> GitHub's default best-match ordering.
>
> Make **two** live searches in that one test. The first is the qualifier-only
> one (`query=""`). The second covers the issue's repro 3 shape — free text plus
> qualifiers: pass the longest all-alphabetic word of at least four characters
> from the anchor issue's title as `query`, together with `state="open"` and the
> anchor label, and assert the call did not return an `Error:` string and that
> the anchor issue number appears in the results.
>
> Skip when no GitHub token is configured, when `IssueManager(...)` raises
> `ValueError` (checkout is not a git repo with a GitHub origin), and when no
> open issue carries a non-`status-` label. If `list_issues` returns an empty
> list, check `_get_repository()` first — `list_issues` swallows API errors, so
> an auth or permission failure must **fail** the test rather than skip it.
>
> Use MCP tools for all file and check operations per `.claude/CLAUDE.md`.
> Verify with `run_pytest_check(extra_args=["-n", "auto"],
> markers=["github_integration"])` — this makes real API calls and needs a
> token. If it cannot run in your environment, say so explicitly rather than
> reporting the step as verified. Also run `run_pylint_check` and
> `run_mypy_check`. This step is one commit.

---

## Live-run result (RESOLVED by [step_4.md](./step_4.md) — history below)

> **Status:** the live test now passes. The analysis below is kept because it is
> the evidence base for step 4's design. Step 4 implements "option 1" /
> "revised recommendation" at the end of this section.

The test was implemented as specified. pylint, mypy and the unit suite pass.
**The live run fails**, and the failure is in production behaviour, not the test:

```
Error: Query must include 'is:issue' or 'is:pull-request': 422
{"message": "Query must include 'is:issue' or 'is:pull-request', "status": "422"}
```

Query sent: `repo:MarcusJellinghaus/mcp-workspace is:open label:"enhancement"`.

Two probes against the live API isolate the cause:

| Query | Result |
|-------|--------|
| `repo:… is:issue is:open label:"enhancement"` | 2 results, **every** line carries `enhancement` and `[open]` |
| `repo:… is:open label:"enhancement"` | HTTP 422 |

So `label:"…"` and `is:open` — the step 2 fix — are accepted and honored by
GitHub exactly as designed. What fails is the *absence* of an `is:issue` /
`is:pull-request` token: `/search/issues` now **requires** one. The summary's
assumption that "`/search/issues` already covers issues and PRs by default"
(and the related `advanced_search=true` "works today" note) is no longer true.

Consequence: after step 1 removed the auto-added qualifiers, **every**
`github_search` call that does not include `is:issue` or `is:pull-request`
inline returns a 422 error. Ironically the old buggy footer `is:issue
is:pull-request` satisfied the requirement — it returned no results (the AND of
both types is empty, this issue's repro), but it did not error.

This cannot be fixed inside step 3, which is test-only, and the obvious fix
reverses step 1's explicit decision, so it needs a call from the maintainer:

1. **Default to `is:issue` when the caller supplies no `is:` token.** Restores
   working searches; changes the default result type.
2. **Send `advanced_search=true`.** Listed as out of scope in the summary, but
   it is the parameter this 422 is steering callers toward, and it keeps both
   issues and PRs in scope. Needs a check that PyGithub can pass it.
3. **Require the caller to pass `is:issue` / `is:pr`** and surface a clear
   error otherwise. Honest, but a breaking change for every existing caller.

Recommendation: option 2 if PyGithub can send the parameter, otherwise option 1.

### Follow-up findings (second run) — two of the premises above are wrong

The 422 reproduces exactly as recorded. Three further live probes and a read of
PyGithub's source change the option set:

**Finding 1 — `is:pull-request` *is* current GitHub syntax.** GitHub's own 422
message names it: `Query must include 'is:issue' or 'is:pull-request'`. Cause A
in [summary.md](./summary.md) asserts "`is:pull-request` is not GitHub syntax;
the qualifier is `is:pr`". That is no longer true on the current API. Step 1's
removal is still correct, but for finding 2's reason, not this one.

**Finding 2 — `is:issue is:pull-request` does not OR; the last token wins.**
Probing the pre-step-1 server (which appends both tokens) with `query="search"`
returned 16 results, **all of them PRs**, though this repo has open issues
matching "search". So the old footer never returned "issues and PRs" — it
silently returned **PRs only**. This is the real defect in Cause A, and it
undercuts the summary's decision #3 rationale ("defaulting to `is:issue` would
silently remove PR discovery"): `github_search` never returned issues at all in
its default shape. Option 1 therefore *flips* a broken default rather than
removing a working capability, and PRs stay reachable via an inline
`is:pull-request`.

**Finding 3 — option 2 is not reachable through `search_issues`.** PyGithub
folds every `**qualifiers` entry into the *query text* as `f"{key}:{value}"`
(`github/MainClass.py`, `Github.search_issues`); only `sort` and `order` become
URL parameters. Passing `advanced_search=True` would append the literal text
`advanced_search:True` to the query, not set the URL parameter. Sending it
requires bypassing the `search_issues` helper and calling the `Requester`
directly — a larger change than the summary's "out of scope" note assumed.

**Revised recommendation: option 1.** Option 2 is not available without dropping
PyGithub's helper, and option 3 breaks every caller to preserve a default that
findings 1 and 2 show was never working. Option 1 is a small, local change in
the same function steps 1 and 2 already touch: when the query carries no
`is:issue` / `is:pull-request` token, add `is:issue`, and say so in the
docstring. It needs its own step, its own mocked tests, and an amendment to
summary.md decision #3 — none of which step 3 may contain.

**Resolution.** After a third run reproduced the identical 422 with no maintainer
decision returned, option 1 was implemented as [step_4.md](./step_4.md) under an
explicitly stated assumption, and step 3's live test now passes. Because option 1
reverses an explicitly recorded design decision and changes this tool's public
default, step 4 carries an open **maintainer review** item; reverting it is a
small, self-contained change if the decision goes the other way.
