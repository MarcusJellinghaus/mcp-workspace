# Implementation review log 3 — Issue #254

`github_search`: invalid qualifier syntax silently returns wrong results.

Continues from [implementation_review_log_2.md](./implementation_review_log_2.md),
which ended after four rounds and a rebuild of the branch onto `origin/main` as a
single integration commit (`379ba40`). This cycle reviews that integrated tree.

## Round 1 (overall round 10) — 2026-08-29

The rebase integration was verified first: main's `#262` result capping
(`islice`, `capped = max(0, max_results)`, the deferred `totalCount` read and
its truncation notice) and the `github_issue_list` over-fetch are byte-identical
to main; main's five capping tests survive in
`test_github_read_tools_pr_search.py`; its superseded `github_search` tests were
dropped and re-created against the new query construction; `FakeSearchResults`
moved to `search_helpers.py` rather than being copied; the duplicated
`setup_server` fixture is gone. No main behaviour lost, nothing duplicated.

**Findings** (six, all low — no critical or medium):

- `server.py:755-794` — the `github_search` docstring has grown to ~36 lines of
  prose before `Args:`, against under 12 for every other tool in the file, and
  FastMCP ships it to every client as the tool description.
- `pr_info/steps/summary.md:113-142` — the committed plan no longer matches the
  tree: it names `test_github_read_tools.py`, which the rebase integration
  replaced, and omits `search_helpers.py` and the integration itself.
- `test_github_search_tool.py:576`, `:604` — the live test asserts the anchor
  with `f"#{number}" in result`, a substring test over the whole rendered block,
  so `#12` passes on a line reading `#123`.
- `test_github_search_tool.py` (12 sites) — `search_issues` stubbed with a bare
  `[]` while three tests in the same module use `FakeSearchResults`. A plain list
  is not the `PaginatedList` contract the code has depended on since `#262`; it
  only works because `totalCount` is guarded behind `if items`.
- `test_github_search_tool.py:1`, `test_github_read_tools_pr_search.py:1` —
  `github_search` coverage lives in two modules with no cross-reference; the new
  module's docstring reads as the sole home.
- `.claude/CLAUDE.md:27` — commit `b082960` adds a `delete_directory` row
  unrelated to #254 and will show in the PR diff.

**Decisions**:

- Docstring length — **skipped**. Every paragraph is a settled
  document-rather-than-code decision from log 2 rounds 2 and 3; the finding is
  about where the text lives, not what it says. Cosmetic, and reshuffling risks
  losing precision the earlier rounds paid for.
- `summary.md` drift — accepted. Log 2 round 2 set the precedent that the plan
  tracks the shipped code; the integration re-broke it.
- Substring anchor assertion — accepted. A false pass in the one test whose
  whole purpose is proving the anchor came back.
- Bare `[]` stubs — accepted. Mechanical, and it makes every double in the
  module honour the contract production depends on.
- Missing cross-reference — accepted. One sentence per module; merging them is
  blocked by the 750-line cap.
- `.claude/CLAUDE.md` row — **skipped**. Harmless and already committed;
  it belongs in the PR description, not a history rewrite.

**Changes**: anchor assertions now match a `#{number} ` line prefix rather than a
substring of the whole block; all twelve bare-list stubs replaced with
`FakeSearchResults([])`; both search-test modules cross-reference each other;
`summary.md` tables renamed to the post-rebase modules, `search_helpers.py`
added, and a "Rebase integration" subsection recorded. No production code
touched.

Checks: format ✅, pylint ✅, mypy ✅, 1626 unit tests passed / 1 skipped,
file-size ✅ (316 files). The live `github_integration` run is deferred to
round 2, which covers the changed live-test assertions.

**Status**: committed.

## Round 2 (overall round 11) — 2026-08-29

Commit `69ed1f8` was verified against its four claims — line-prefix anchor
assertions, twelve `FakeSearchResults([])` conversions with zero remaining bare
lists, cross-references in both module docstrings, and `summary.md` matching the
tree. The live `github_integration` run deferred from round 1 passed: 24 of 24.

**Findings** (three, all low):

- `server.py:799-864` — `github_search` holds ~65 lines of GitHub query-syntax
  logic in the MCP protocol layer, which `docs/ARCHITECTURE.md:48` reserves for
  tool registration and handlers; every other GitHub tool delegates to a
  manager. Pre-existing in kind (~10 lines before this branch) but multiplied
  by it.
- `test_github_search_tool.py:643-644`, `:676-677` — the two parametrized live
  tests assert `result != "No results found."` unconditionally, while the label
  test distinguishes "repo has no matching items" (skip) from "API unreachable
  or token lacks access" (fail). A checkout with no PRs, or no closed issues,
  fails with no diagnosis.
- `test_github_search_tool.py:143-145` — three assertions strictly implied by
  the exact-equality check above them.

**Decisions**:

- Layering — **skipped for this PR, recommended as a follow-up issue**. The plan
  decided against a `build_search_query` helper deliberately, `lint-imports`
  passes all 9 contracts, and the concern is pre-existing in kind. Extracting it
  properly means a new module under `github_operations/` and moving the unit
  tests off `server.py` — meaningful scope that does not belong in a bug fix.
- Live-test guards — accepted. It mirrors a guard the module already has, and
  the whole point of these tests is that a real result came back; a failure that
  cannot distinguish "no PRs here" from "no access" undercuts that.
- Redundant assertions — accepted in part. The two positive `in` checks go; the
  `"labels:bug,urgent" not in` check stays as the named #254 regression marker.

**Changes**: the fail-vs-skip guard extracted into a module-level
`_skip_or_fail_on_empty` helper and applied to all three live tests; two implied
assertions dropped from `test_github_search_multiple_labels`, with a comment
naming the surviving one as the regression marker. No production code touched.

Checks: format ✅, pylint ✅, mypy ✅, 1626 unit tests passed / 1 skipped, live
`github_integration` run ✅ (24 passed — the new guards stayed dormant, so the
live assertions still ran for real), file-size ✅ (316 files).

**Status**: committed.

## Round 3 (overall round 12) — 2026-08-29

**Findings** (one medium; nothing else):

- `test_github_search_tool.py:661-664`, `:697-700` — medium — the guard added in
  round 2 converts the exact regression these two tests exist to catch into a
  skip. It distinguishes "API reachable" from "API unreachable"; it does not
  establish that the repository genuinely has no matching items, only that *this
  search* came back empty. If `is:pr`, `type:pr`, `type:issue`, `state:open` or
  `state:closed` stopped matching, GitHub answers with an empty set rather than
  a 422, `_get_repository()` still succeeds, and the test skips green.

Verification of `0289412` otherwise passed: the helper's fail branch is genuine
(`_get_repository()` returns `None` on `GithubException`), `NoReturn` is honest,
no test was weakened into always-skipping, and the two dropped assertions in
`test_github_search_multiple_labels` are strictly implied by the exact-equality
check above them.

**Decisions**:

- Accepted, and it reverses part of round 2's decision. Round 2 applied the
  guard to all three live tests; that was right only for
  `test_github_search_live_label_and_state_filters`, where the guard sits on the
  independent `list_issues` anchor-discovery step and the search's own emptiness
  stays a hard assertion. In the other two the search result *is* the assertion,
  and an empty one is precisely the silent-wrong-answer failure #254 exists to
  fix — the same reasoning that makes the production code reject
  `type:pull-request` rather than forward it.
- The review's alternative — probing emptiness through the REST listing instead
  of `/search/issues` — was not taken. Reverting the two call sites restores the
  signal fully and is the smaller change.
- Noted and folded in: with those two reverted, `_skip_or_fail_on_empty` had a
  single call site, so it was inlined back and deleted. That also removed the
  duplicated `try/except ValueError` the review flagged as a nit.

**Changes**: both parametrized live tests assert
`result != "No results found."` again, with a message naming the token under
test; the label test's guard inlined; helper and its `NoReturn` import deleted.
Everything else from `0289412` untouched. No production code touched.

Checks: format ✅, pylint ✅, mypy ✅, 1626 unit tests passed / 1 skipped, live
`github_integration` run ✅ (24 passed, 0 skipped — scoped to the search module,
9 of 9 passed, so the two restored assertions genuinely executed), file-size ✅.

**Status**: committed.

## Round 4 (overall round 13) — 2026-08-29

**Findings**: NO FINDINGS. Commit `87890ad` verified against all four of its
claims with nothing left dangling: the `NoReturn` import is gone and no other
symbol needs it, `_skip_or_fail_on_empty` has zero references left in the tree,
the inlined guard in the label test sits after both prerequisites and still
distinguishes "empty repo" from "no access", and both parametrized live tests
carry the hard assertion with no comment still referring to a skip path.

The full branch diff was re-read against `main` and specifically re-checked:
regex boundary behaviour (`(?![\w-])` with the `(?:^|\s)` prefix), validation
ordering (state → `type:pull-request` → labels → assignee, all before the
`IssueManager` is constructed, matching the `assert_not_called` assertions), the
`state="all"` no-token path, label quoting for colon-bearing labels, the
`setup_server` fixture's save-and-restore of `server._project_dir`, and that
every mocked test dropped from `test_github_read_tools_pr_search.py` has an
equivalent in `test_github_search_tool.py`.

**Decisions**: nothing to accept — zero code changes, so the review loop ends
here.

**Status**: no changes needed.

## Final Status

Four rounds ran in this cycle (rounds 10–13 counting logs 1 and 2), producing
three commits, all test-and-docs only:

| Commit | Content |
|--------|---------|
| `69ed1f8` | Line-prefix anchor assertions in the live test; twelve bare-list stubs replaced with `FakeSearchResults([])`; cross-references between the two search-test modules; `summary.md` refreshed for the post-rebase layout |
| `0289412` | Extract the live-test empty-result guard into a helper and apply it; drop two assertions implied by an exact-equality check |
| `87890ad` | Restore the hard empty-result assertions on the two parametrized live tests; inline the guard back into the label test and delete the helper |

The cycle opened by verifying the rebase integration — main's `#262` result
capping, deferred `totalCount` read and truncation notice all survive unchanged,
its five capping tests keep their home in `test_github_read_tools_pr_search.py`,
`FakeSearchResults` moved rather than being copied, and the duplicated
`setup_server` fixture is gone.

No production code changed in this cycle. The through-line across the three
commits is the same standard the branch itself sets: a test that cannot tell a
genuine empty result from a broken one is the failure #254 exists to fix.
Commits `0289412` and `87890ad` are the two halves of settling exactly where
that line falls — the guard is right on the label test's independent
anchor-discovery step and wrong on a search result that *is* the assertion.

**Checks on the final tree**: pylint ✅, mypy ✅ (strict), 1626 unit tests
passed / 1 skipped, live `github_integration` run ✅ (24 passed, 0 skipped),
black/isort ✅, ruff ✅, file-size ✅ (316 files within 750 lines), vulture ✅
(no output), lint-imports ✅ (9 contracts kept, 0 broken).

**Deferred to a follow-up issue, not a merge blocker**: `github_search` holds
~65 lines of GitHub query-syntax logic in `src/mcp_workspace/server.py`, which
`docs/ARCHITECTURE.md:48` reserves for tool registration and handlers. Every
other GitHub tool delegates to a manager under `github_operations/`. It is
pre-existing in kind (~10 lines before this branch) and multiplied by it;
`lint-imports` keeps all 9 contracts, so nothing is violated today. Extracting a
`build_search_query` helper means a new module and moving the unit tests off
`server.py` — scope that does not belong in a bug fix.

**Outstanding**: CI on the pushed branch is PASSED, but the branch is `BEHIND`
`origin/main` and needs a rebase before the PR is raised.
