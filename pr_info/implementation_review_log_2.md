# Implementation review log 2 — Issue #254

`github_search`: invalid qualifier syntax silently returns wrong results.

Continues from [implementation_review_log_1.md](./implementation_review_log_1.md),
which ended after 5 rounds with a rebase handoff.

## Round 1 (overall round 6) — 2026-08-29

**Findings** (all low; rounds 1–4 of log 1 re-verified as genuinely resolved):

- `server.py:787-796` — `type:pull-request` is forwarded although the code already knows GitHub matches nothing against it, so the caller gets `No results found.` — indistinguishable from a genuine empty result.
- `server.py:811` — `label.replace('"', '\\"')` relies on backslash escaping inside a quoted GitHub qualifier, which is not documented GitHub syntax and is the only relied-on spelling on this branch with no live test.
- `server.py:746` — the docstring summary line ("Search GitHub issues and pull requests") contradicts the paragraph below it ("the default is therefore issues only").
- `test_github_search_tool.py:14-24` / `test_github_read_tools.py:20-24` — the step-5 file split duplicated the autouse `setup_server` fixture and the copies diverged; only one restores `server._project_dir`.

**Decisions**: all four accepted. Each is the issue's own failure mode — a silently wrong or unverified qualifier — or a direct consequence of this branch's changes, and all four fixes are bounded. Nothing escalated.

**Changes**:

- `type:pull-request` is rejected before the API call with an explicit error, alongside the existing `state` validation. Rejection reuses the type-detection regex's word boundaries, so `type:pull-requests` and `release:type:pull-request` stay free text.
- Backslash escaping dropped; a label containing a double quote is rejected before the API call.
- Docstring summary line corrected; the label-quote rejection documented on the `labels` argument.
- The save-and-restore `setup_server` fixture moved into `tests/github_operations/conftest.py`, both module-local copies deleted, each module opting in via `pytestmark`. Kept non-autouse deliberately: `project_dir` does a `shutil.copytree` per test, so package-wide autouse would add a directory copy to every test in the package.

Checks: pylint ✅, mypy ✅, 1591 unit tests passed / 1 skipped, live `github_integration` run ✅ (24 passed), black/isort ✅, file-size ✅.

**Status**: committed.

## Round 2 (overall round 7) — 2026-08-29

**Findings**:

- `server.py:807-812` — medium — a PR-only qualifier other than the five recognised spellings (`is:merged`, `is:draft`, `base:`, `head:`, `review:`, `merged:`) does not suppress the `is:issue` default, so `is:issue` is ANDed on and the search cannot match — returning `No results found.` indistinguishable from a genuine empty result.
- `server.py:828` — low — `assignee` is interpolated unquoted and unvalidated; a value containing whitespace splits into `assignee:john` plus a stray free-text term, silently narrowing results. The only caller-supplied qualifier value left unchecked.
- `server.py:779` — low — the `state` vocabulary check is case-sensitive while every inline qualifier check uses `re.IGNORECASE`, so `state="Open"` is rejected while `IS:OPEN` inline is honoured.
- `server.py:830-833` — low — `sort` and `order` are forwarded unvalidated; GitHub silently ignores an unrecognised `sort` and falls back to relevance ordering.
- `server.py:784` — low — the `type:pull-request` rejection has no escape hatch, so the literal string cannot be searched as free text.
- `pr_info/steps/summary.md` — low — the plan no longer describes the shipped code: the file table omits `tests/github_operations/test_github_search_tool.py` and `conftest.py`, and none of the review rework is recorded.

**Decisions**:

- PR-only qualifiers — **accepted as documentation only**. Suppressing the default for those tokens would leave a query naming no result type at all, which step 3 showed GitHub answers with a 422; a code fix therefore means inferring `is:pull-request` from an open-ended qualifier list. That is scope growth beyond #254 with live-verification cost, and a half-covered list is a worse contract than none. The docstring now names the five suppressing spellings exactly and says a PR-only qualifier needs an explicit `is:pull-request`.
- `assignee` validation — accepted. Three lines mirroring the label check, and it closes the last unchecked qualifier value.
- `state` case-sensitivity — accepted. One-line inconsistency in the same function's contract.
- `sort` / `order` validation — **skipped**. Pre-existing and never part of the broken query construction; out of scope per the knowledge base.
- `type:pull-request` escape hatch — accepted as a docstring line, folded into the work above.
- `summary.md` drift — accepted in part: the plan is corrected to match the shipped code. `TASK_TRACKER.md` left alone, since review rework belongs in this log.

**Changes**: docstring rewritten to name the five suppressing spellings and the `type:pull-request` rejection; `assignee` rejected before the API call when it contains whitespace; `state` matched and emitted case-insensitively via a normalized value; `summary.md` given a corrected "Created" table and a "Review rework" section. Two new parametrized tests (6 cases).

Checks: pylint ✅, mypy ✅, 1597 unit tests passed / 1 skipped, live `github_integration` run ✅ (24 passed), black/isort ✅, file-size ✅.

**Status**: committed.

## Round 3 (overall round 8) — 2026-08-29

**Findings** (all low):

- `pr_info/steps/summary.md:138` — the "Review rework" section links to `implementation_review_log_2.md`, which is untracked, so the branch ships a committed document pointing at a file not in the tree.
- `server.py:840-842` — the label loop has no emptiness check, so `labels=["bug", ""]` emits `label:""`. Confirmed by scratch probe. An unrepresentable value is forwarded instead of rejected, giving an empty result indistinguishable from a genuine one — the class already closed for quote-bearing labels and whitespace assignees.
- `server.py:823-828`, `:835-837` — both regexes anchor on `(?:^|\s)`, so a negated qualifier is invisible: the character before `is:` is `-`. Confirmed by probe — `query="fix -is:issue"` sends `... is:issue fix -is:issue`, which can never match. Same for `-is:open` against the `state` parameter.

**Decisions**:

- summary.md link — **skipped, self-resolving**. The log is untracked by design; this skill commits it at the end of the cycle in a separate commit, at which point the link resolves.
- Blank label — accepted. Two lines in the existing validation block, and it closes the last unrepresentable qualifier value.
- Negated qualifiers — **accepted as a docstring clause only**. Extending the regexes to see `-is:issue` would suppress the default and leave a query naming no result type, which step 3 showed GitHub answers with a 422 — the same reasoning that settled round 2's PR-only-qualifier finding.

**Changes**: empty or whitespace-only labels rejected before the API call alongside the quote check; docstring states that a negated qualifier names neither a type nor a state and so suppresses neither the `is:issue` default nor the `state` argument; `summary.md` records both. One new parametrized test (3 cases).

Checks: pylint ✅, mypy ✅, 1600 unit tests passed / 1 skipped, live `github_integration` run ✅ (24 passed), black/isort ✅, file-size ✅.

**Status**: committed.

## Round 4 (overall round 9) — 2026-08-29

**Findings**: NO FINDINGS. The blank-label rejection and the negated-qualifier docstring from `7b10ec7` were both verified correct, including a scratch probe confirming `-type:pull-request` bypasses the rejection exactly as the docstring now documents.

Examined and dismissed, recorded so it need not be redone: padded label values (`labels=[" bug "]` is sent as `label:" bug "` — calling that a defect requires asserting GitHub does not trim inside a quoted qualifier, which is not live-verified); whitespace-only `query`; the docstring's "contradicted by the token this tool adds" being imprecise for `-is:open` when no `state` argument is passed. `re` and `Dict` are both still live in `server.py`.

**Decisions**: nothing to accept — zero code changes, so the review loop ends here.

**Status**: no changes needed.

## Final Status

Four review rounds ran in this cycle (rounds 6–9 counting log 1), producing three code commits plus one tooling commit:

| Commit | Content |
|--------|---------|
| `023f117` | Reject `type:pull-request`; reject labels containing a double quote; fix the docstring summary line; move `setup_server` into `tests/github_operations/conftest.py` |
| `34767f9` | Reject an `assignee` containing whitespace; match `state` case-insensitively; document which spellings suppress the `is:issue` default |
| `7b10ec7` | Reject empty and whitespace-only labels; document negated qualifiers |
| `c82d83d` | Whitelist `pytestmark` for vulture |

The through-line across all three code commits is the issue's own standard: a qualifier value this tool cannot represent is now rejected before the API call rather than forwarded to produce an empty result indistinguishable from a genuine one. Three findings were settled as documentation rather than code — PR-only qualifiers, negated qualifiers, and the `type:pull-request` free-text limitation — each because suppressing the `is:issue` default would leave a query naming no result type, which GitHub answers with a 422.

**Checks on the final tree**: pylint ✅, mypy ✅ (strict), 1600 unit tests passed / 1 skipped, live `github_integration` run ✅ (24 passed), black/isort ✅, file-size ✅ (all files within 750 lines), vulture ✅ (clean), lint-imports ✅ (9 contracts kept, 0 broken).

**Outstanding**: the branch is `BEHIND` `main` and needs a rebase before the PR. CI is green and no PR exists yet.

## Rebase integration onto `main` — 2026-08-29

A commit-by-commit rebase was attempted and abandoned. It resolved the first
`server.py` conflict cleanly but stalled at commit 16 of 28 on a structural
collision: `main` had split `tests/github_operations/test_github_read_tools.py`
into `_issues.py` + `_pr_search.py`, while this branch had split the same file
into `test_github_read_tools.py` + `test_github_search_tool.py`. On top of that,
`#262` rewrote the `github_search` tests inside main's half against the
unfixed query behaviour this branch replaces. Nine of the branch's commits touch
the same function, so replaying them meant resolving the same semantic conflict
nine times — the skill's own abort rule 4.

The branch was instead rebuilt on `origin/main` as a single integration, with
`backup/254-pre-integration` retained at the pre-rebase tip `afe8cd2`.

**How the two sides were reconciled:**

- **`server.py`** — main's file is the base, so `#262`'s `islice` capping,
  `capped = max(0, max_results)`, `totalCount` notice and the `github_issue_list`
  over-fetch survive untouched. This branch's validation block, query
  construction and docstring were applied into it; the `has_qualifier` footer
  main still carried was dropped, which is what this branch exists to do.
- **Search tests** — main's five pagination and truncation-notice tests keep
  their home in `_pr_search.py`; they assert result capping, which this branch
  does not change. Main's `basic` / `empty` / `with_qualifiers` /
  `qualifier_injection` / `error` / `no_repo` / `issue_vs_pr_indicator` tests
  were dropped as superseded — they assert the removed `(auto-added: ...)`
  footer and the old qualifier folding, and `test_github_search_tool.py` covers
  the same ground with exact-query assertions.
- **`FakeSearchResults`** — main's PaginatedList double is now needed by both
  modules, so it moved to `tests/github_operations/search_helpers.py` rather
  than being copied. Non-empty mocks in `test_github_search_tool.py` had to
  adopt it: under `#262` a plain list has no `totalCount`.
- **Fixture duplication** — main's layout reintroduced the autouse
  `setup_server` in two modules. Both now opt into the shared conftest fixture
  via `pytestmark`, preserving the round-1 review fix.

**Checks after integration**: pylint ✅, mypy ✅ (strict), 1626 unit tests
passed / 1 skipped, live `github_integration` run ✅ (24 passed), black/isort ✅,
vulture ✅, lint-imports ✅ (9 contracts kept), file-size ✅ (315 files).
