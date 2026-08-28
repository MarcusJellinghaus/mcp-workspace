# Summary — Issue #257: Truncation notices name the cap and the parameter that lifts it

## Goal

Every truncation notice in the codebase currently prints the **total** length where a
reader expects the **cap**, and never names the parameter that lifts it. Two tools
(`github_issue_list`, `github_search`) truncate with **no notice at all**, because their
notice is guarded by a condition their only callers make impossible.

This work changes **messages only**, plus **one render-order fix** in `pr_feedback`.
No new tool parameters, no new capabilities, no new modules.

## House style (single source of truth)

Every notice states **`showing X of Y`**, then names the parameter that lifts the cap
with a **pasteable value**.

Three documented exceptions, all in CI-log territory, where a pasteable value would be
dishonest because one budget is shared across up to three failed jobs: the two
`ci_log_parser` markers and the `## Other failed jobs` header name `max_log_lines`
**without** a value.

Internal caps (`tree_listing`, `search`, `file_operations`) get an improved message and a
code comment recording that the cap is deliberate, but **no new parameter**.

## Architectural / design changes

The change is deliberately architecture-neutral. Nothing moves between layers, no module
is created, and `docs/ARCHITECTURE.md`, `.importlinter` and `tach.toml` are untouched.
Six design decisions are worth recording:

1. **The two `truncate_output` functions stay separate.**
   `github_operations/formatters.py` and `git_operations/output_filtering.py` each own a
   `truncate_output`. They will emit the identical house-style string, and the DRY reflex
   is to hoist it into a shared helper. We deliberately do not. The two functions sit in
   different architecture layers — per `docs/ARCHITECTURE.md`, `github_operations` may
   import `git_operations` but not the reverse — so a shared helper would mean a new
   utility module plus `.importlinter`/`tach.toml` updates for a one-line string. Two
   independent f-strings is the cheaper and more maintainable answer. The intent is that
   the pattern is **copyable**, not shared.

2. **One new private helper: `ci_log_parser._truncation_marker(kept, total)`.**
   The marker is emitted from two places — `truncate_ci_details` and, inline, from
   `build_ci_error_details`. They are byte-identical today; changing one would ship two
   spellings of one marker. The helper takes two arguments, not three: `omitted` is
   always `total - kept`, so passing it separately would reintroduce the drift the helper
   exists to prevent.

3. **`format_search_results` gains an optional `total_count`; `format_issue_list` gains
   nothing.** The two tools learn "more exist" by different routes because only one of
   them can know the real total. GitHub's search endpoint returns `total_count` in the
   first page payload and PyGithub exposes it as `PaginatedList.totalCount` with no extra
   request — so search states an **exact** total. Issue listing has no equivalent count,
   so it over-fetches `max_results + 1` and uses the surplus item to prove more exist,
   rendering `30+`. The formatter signature for `format_issue_list` is unchanged; only
   its caller changes.

4. **`max_log_lines` is threaded to the render-stage CI cap (step 3).** The marker names
   `max_log_lines`, so that parameter must be the one that governs the cut. It governs
   the *build* stage today, but `async_poll_branch_status` calls `format_for_llm()`
   without `max_lines` (`branch_status_polling.py:124, 154`), so the second cut in
   `format_report_for_llm` → `truncate_ci_details` uses a hard-coded 300 that
   `max_log_lines` cannot lift. Both call sites now pass `max_lines=max_log_lines`. No
   signature changes; both defaults are 300, so default-sized reports are unchanged.

5. **`github_search` stops before the surplus item (step 5).** The `i >= max_results`
   guard pulls item `max_results` before breaking, which fetches a second search page
   only to discard it. `islice(results, max_results)` stops without that pull, so
   `totalCount` really does cost nothing extra.

6. **`_truncate_body` stays pure.** The `pr_feedback` footer condition is computed by
   `format_pr_feedback` itself, by comparing `_truncate_body`'s output against its input
   (`_truncate_body` returns the input unchanged when it does not cut). No tuple return,
   no marker-substring sniffing, no threshold duplicated.

### Behavioural change: `pr_feedback` render order

Current order is unresolved threads → conversation comments → changes-requested →
alerts, under a single 20-item cap. Conversation comments never drain — they accumulate
and nothing removes them — yet they sit ahead of the two sections that decide the merge
verdict. On a PR with 25 comments the budget fills with threads plus comments and alerts
never render at all.

New order: **unresolved threads → changes-requested → alerts → conversation comments.**
The 20-item cap stays; the non-draining section moves to the back where it cannot starve
the others.

This changes rendered output only. `blocks_merge` is computed from the feedback data
(`pr_feedback.py:126-130`), not from the rendered text, so a truncated display never
turned a blocked PR into a clean one — what was lost was the detail of *why*. The
reorder also cannot save alerts from thread-heavy overflow: with the single shared cap
kept, more than 20 unresolved threads still starve alerts. That is accepted; the fix
targets the non-draining section, which is the case that occurs in practice.

### Note on the `pr_feedback` cap line and footer

When the item cap fires, two lines mention `github_pr_view(include_comments=True)`. This
is intentional and not redundant: the cap line offers the **full list of items**, the
footer offers the **full text of a body that was cut**. `include_comments=True` must be
spelled out at both sites because it defaults to `False` on `github_pr_view`
(`server.py:662`), unlike `github_issue_view`.

## Files created

| Path | Purpose |
|---|---|
| `pr_info/steps/summary.md` | This document |
| `pr_info/steps/step_1.md` … `step_9.md` | One self-contained step each |

## Files modified

### Source

| File | Change |
|---|---|
| `src/mcp_workspace/github_operations/formatters.py` | `truncate_output` message (step 1); `format_issue_list` notice (step 4); `format_search_results` notice + `total_count` param (step 5) |
| `src/mcp_workspace/git_operations/output_filtering.py` | `truncate_output` message (step 2) |
| `src/mcp_workspace/github_operations/ci_log_parser.py` | New `_truncation_marker` helper, both call sites, `## Other failed jobs` header (step 3) |
| `src/mcp_workspace/checks/branch_status_polling.py` | Pass `max_lines=max_log_lines` to `format_for_llm` at both call sites (step 3) |
| `src/mcp_workspace/server.py` | `github_issue_list` over-fetch (step 4); `github_search` uses `islice` + reads `totalCount` (step 5) |
| `src/mcp_workspace/checks/pr_feedback.py` | Render order, body/cap messages, conditional footer (step 6) |
| `src/mcp_workspace/file_tools/tree_listing.py` | `_truncate` summary message + comment (step 7) |
| `src/mcp_workspace/file_tools/search.py` | Line-truncation message + comment (step 8) |
| `src/mcp_workspace/file_tools/file_operations.py` | Code comment only, message unchanged (step 9) |

### Tests

| File | Change |
|---|---|
| `tests/github_operations/test_formatters.py` | Steps 1, 4, 5 |
| `tests/git_operations/test_output_filtering.py` | Step 2 |
| `tests/github_operations/test_ci_log_parser.py` | Step 3 |
| `tests/checks/test_branch_status_polling_orchestrator.py` | Step 3 |
| `tests/github_operations/test_github_read_tools.py` | Steps 4, 5 |
| `tests/checks/test_branch_status_pr_feedback.py` | Step 6 |
| `tests/file_tools/test_tree_listing.py` | Step 7 |
| `tests/file_tools/test_search.py` | Step 8 |

### Deliberately not modified

`docs/ARCHITECTURE.md`, `.importlinter`, `tach.toml`, `vulture_whitelist.py` — no new
modules or boundaries. `tests/git_operations/test_read_operations.py` — its four
`assert "[truncated" in result` assertions survive unchanged, because the new
`output_filtering` notice still starts with `[truncated`.

## Step index

All nine steps are **mutually independent** and may be implemented in any order. Each is
one commit: tests + implementation + all three checks passing.

| Step | Scope | Test churn |
|---|---|---|
| 1 | `formatters.truncate_output` — feeds `github_issue_view` / `github_pr_view` | `test_formatters.py:77` |
| 2 | `output_filtering.truncate_output` — feeds the `git` tool | `test_output_filtering.py:190, 199` |
| 3 | `ci_log_parser` — marker helper, both sites, "Other failed jobs" header, plus `max_log_lines` threaded to the render-stage cap | `test_ci_log_parser.py:42, 49, 351`, new polling test |
| 4 | `github_issue_list` silent truncation | `test_formatters.py:181`, `test_github_read_tools.py:233` |
| 5 | `github_search` silent truncation | `test_formatters.py:363` |
| 6 | `pr_feedback` reorder + messages + conditional footer | `test_branch_status_pr_feedback.py:199, 362` |
| 7 | `tree_listing` summary message | `test_tree_listing.py:331` |
| 8 | `search.py` line-truncation message | `test_search.py:280, 303` |
| 9 | `file_operations` code comment only | none |

## Conventions

- **Em dash.** Match each file's existing convention: `output_filtering.py` uses a
  literal `—`, `tree_listing.py` uses the `—` escape. Do not change a file's
  convention.
- **TDD.** In every step, update or add the tests first, watch them fail, then implement.
- **Checks.** After each edit run all three, per `CLAUDE.md`:
  `mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check`
  (with `extra_args=["-n", "auto", "-m", "not git_integration and not
  claude_cli_integration and not claude_api_integration and not formatter_integration and
  not github_integration and not langchain_integration"]`),
  `mcp__mcp-tools-py__run_mypy_check`.
- **Formatting.** Run `./tools/format_all.sh` before committing.

## Acceptance criteria coverage

| Criterion | Step(s) |
|---|---|
| Every notice states the applied cap and the total, distinguishably | 1, 2, 3, 4, 5, 6, 7, 8 |
| Notices name the lifting parameter with a pasteable value, except the two `ci_log_parser` markers and the "Other failed jobs" header | 1, 2, 3 |
| No notice names a parameter its caller does not accept | 1, 2, 3, 4, 5 |
| `github_issue_list` / `github_search` emit a notice when capped; search states the exact total | 4, 5 |
| `pr_feedback` renders alerts and changes-requested ahead of conversation comments | 6 |
| `pr_feedback` footer appears only when a body was truncated or the cap fired | 6 |
| Tests assert both numbers + `max_lines`; list/search notices; alerts survive comment overflow | 1, 4, 5, 6 |
| Each internal-cap site carries a comment naming the alternative | 6, 7, 8, 9 |
