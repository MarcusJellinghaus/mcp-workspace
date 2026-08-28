# Implementation review log 2 — Issue #257

Run started 2026-08-28, after the branch was rebased onto `main`.
Review run 1 (`implementation_review_log_1.md`) ended at round 3 with no findings but a
pending rebase; this run re-reviews the rebased branch.

## Round 1 — 2026-08-28

**Findings** (all low severity; no high or medium found):

1. `github_operations/formatters.py:110` — `github_issue_list(max_results=0)` against a
   non-empty repo returns `No issues found.`, which the caller's own over-fetch disproves.
2. `github_operations/formatters.py:193` — `format_search_results` has no internal
   `max(0, max_results)` clamp, unlike its sibling `format_issue_list`; unreachable today
   because `server.py:804` clamps externally.
3. `github_operations/formatters.py:49` — `github_issue_view(max_lines=0)` opens with two
   blank lines before the notice.
4. `github_operations/ci_log_parser.py:403` — `build_ci_error_details` never charges the
   "Other failed jobs" section against `lines_used`, so output can exceed `max_lines`.
5. `tests/checks/test_branch_status_polling_orchestrator.py:493` — the new
   `max_lines=max_log_lines` test leaves `ci_timeout=0` and so only reaches the second
   `format_for_llm` call site; the `branch is None` site is uncovered.

**Decisions**:

- **Accept 1.** Exactly the "notice says the opposite of what it means" defect #257 exists
  to remove, and introduced by the round-2 fix of the previous run.
- **Skip 2.** Defensive code for a caller error that cannot occur; speculative per
  `software_engineering_principles.md`.
- **Skip 3.** Cosmetic whitespace on a degenerate input, not a misleading statement.
- **Skip 4.** Pre-existing budget-accounting defect. Fixing it changes budget behaviour,
  outside #257's declared "messages only, plus one reorder" scope.
- **Accept 5.** Coverage gap on a line this branch changed; cheap.

**Changes**: `format_issue_list` now judges emptiness on the over-fetched list, so
`No issues found.` is returned only for a genuinely empty listing; a cap of 0 over a
non-empty repo renders the notice alone. New test covers both halves of the distinction.
New polling test patches `get_current_branch_name` to `None` to reach the detached-HEAD
call site and asserts `max_lines` is threaded there too.

**Status**: committed.

## Round 2 — 2026-08-28

**Findings**:

1. `server.py:804` (`github_search`), test at `test_github_read_tools_pr_search.py:426` —
   medium — `github_search(max_results=0)` returns `No results found.` over a non-empty
   result set: the same false notice commit `1828279` had just removed from the sibling
   `github_issue_list`, with a test asserting the wrong output as correct.
2. `github_operations/formatters.py:128` — low — the zero-cap notice renders
   `showing 0 of 0+ results`, although the branch is reachable only when the caller's
   over-fetch already proved at least one issue exists.
3. `github_operations/formatters.py:128` vs `:140` — low — `format_issue_list` emits two
   spellings of one notice, the drift `_truncation_marker` exists elsewhere to prevent.

**Decisions**: all three accepted; 2 and 3 folded into one change. Fixing the zero-cap lie
in one sibling tool and not the other would have been worse than fixing neither. Fixing 2
without 3 would have left the duplicated spelling in the line being edited.

Constraint given to the engineer: no extra API request. With a cap of 0 no search page is
fetched, so `PaginatedList.totalCount` is not free there — the message must claim neither
a total it never observed nor an empty result set.

**Changes**:

- `github_search` hoists the clamp into a `capped` local and branches three ways: results
  present, nothing collected because the cap was 0, and nothing collected with a positive
  cap. The zero-cap notice reads `... showing 0 of an unknown total — a max_results cap of
  0 suppressed the output; raise max_results to see results.` No `totalCount` read happens
  on either empty path, and the test asserts `total_count_reads == 0`.
- `format_issue_list` loses its separate zero-cap early return. One notice construction
  now serves every cap, guarded by `len(issues) > len(displayed)`, with the lower bound
  taken from `len(issues)` — the largest total the function can prove.

**Status**: committed.

## Round 3 — 2026-08-28

**Findings** (all low; no high or medium):

1. `server.py:653` — the over-fetch comment still says the formatter renders `30+`, but
   `20a6868` changed the lower bound to `len(issues)`, so the default render is `31+`.
2. `server.py:818` — the comment justifies skipping the `totalCount` read by claiming no
   page was fetched on an empty result set; that is false with a positive cap, where
   `islice` pulls, page 1 is fetched and `totalCount == 0` is cached.
3. `server.py:823` — the zero-cap search notice is the only user-facing truncation string
   built in the protocol layer; its sibling lives in `formatters.py`.
4. `checks/pr_feedback.py:117` — the literal `github_pr_view(include_comments=True)`
   appears twice in one function despite the new `_FULL_TEXT_HINT` constant.
5. `github_operations/formatters.py:121` — the new comment asserts `No issues found.`
   "must mean the listing was empty", but `@_handle_github_errors(default_return=[])`
   routes a swallowed API failure to the same branch.

**Decisions**:

- **Accept 1, 2, 5.** All three are comments this branch wrote that state something the
  code does not do. A wrong comment about API-call cost (2) is the kind a maintainer
  trusts without re-deriving.
- **Accept 3.** Placement, not only drift risk: `formatters.py` owns every other notice.
- **Skip 4.** Extracting a bare string fragment to remove one duplicate literal reads
  worse than the duplication, and `summary.md` already records both mentions as
  deliberate — the cap line offers the full item list, the footer the full body text.
- The error swallowing behind finding 5 is pre-existing and stays out of scope; only the
  comment was corrected.

**Changes**: `format_search_results` now owns both empty renders, telling a clamped cap of
0 apart from a genuinely empty result set via `max_results <= 0`; the server's three-way
branch collapses to one call passing `results.totalCount if items else None`, so no
`totalCount` read is added on either empty path and the `total_count_reads == 0` assertion
still holds. A formatter-level test covers the moved notice, so both sibling zero-cap
notices are tested in one suite. Three comments corrected.

**Status**: committed.

## Round 4 — 2026-08-28

**Findings**: NO FINDINGS.

The reviewer independently re-verified the load-bearing claims rather than trusting the
comments: the no-extra-request guarantee on both empty search paths, the clamp arithmetic
in `truncate_ci_details` and `build_ci_error_details` (head and tail can never overlap),
the `pr_feedback` footer having no false negative, `search.py` reporting the pre-slice
length, and every notice naming only parameters its reachable tool accepts —
including that `tree_listing`'s `path=`/`dirs_only=` hint is never rendered by
`list_reference_directory`, which does not go through the tree renderer.

**Decisions**: none required.

**Changes**: none.

**Status**: no changes needed — review loop closed.

## Final Status

Four rounds run in this review run (rounds 1–3 produced changes, round 4 was clean).

**Commits produced**:

| Commit | Subject |
|---|---|
| `1828279` | `fix(github_operations): honest notice when github_issue_list cap is 0` |
| `20a6868` | `fix(github_operations): make zero-cap truncation notices honest` |
| `7a11be8` | `fix(github_operations): move zero-cap search notice into formatters` |

**Theme.** Every accepted finding in this run was the same defect the issue exists to
remove, resurfacing at the degenerate cap: a notice that states something the code cannot
know. First `github_issue_list(max_results=0)` asserting `No issues found.` over a
non-empty repo, then the identical lie in `github_search`, then three comments claiming
premises the code does not hold. The fixes converged on one rule — a notice may state only
what the call actually observed, and a cap of 0 observes nothing.

**Final checks**: pylint clean, mypy clean, pytest 1590 passed / 1 skipped, vulture no
output, lint-imports 9 contracts kept / 0 broken.

**Open items**: none blocking. Three findings were recorded as deliberate skips —
the unreachable negative-cap path in `format_search_results`, the double blank line at
`max_lines=0`, and the twice-written `github_pr_view(include_comments=True)` literal. One
pre-existing defect was noted and left alone as outside #257's scope: `build_ci_error_details`
never charges its "Other failed jobs" section against `lines_used`, so a report can exceed
`max_lines` and, with a sub-300 cap, show two truncation markers. Worth a separate issue.
