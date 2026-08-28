# review-implementation review log 1

## Round 1 — 2026-08-28
**Findings**:
I'll start by loading the tools I need and gathering context.`src/mcp_workspace/github_operations/formatters.py:106` — medium — `format_issue_list`'s notice only fires because `github_issue_list` over-fetches `max_results + 1`; neither the signature nor the docstring records that invariant, so any future caller passing an exactly-capped list silently reintroduces the no-notice bug this issue exists to fix.
`src/mcp_workspace/server.py:825` — low — `getattr(results, "totalCount", None)` is a production fallback that exists solely to keep list-based test doubles working; PyGithub's `search_issues` always returns a `PaginatedList` with the attribute.
`tests/github_operations/test_github_read_tools_pr_search.py:326` — low — no test covers design note 5's claim that `islice` stops without pulling item `max_results + 1` (the sole justification for replacing the `enumerate` guard); a generator-based double counting pulls would verify it.
`src/mcp_workspace/github_operations/ci_log_parser.py:54` — low — `truncate_ci_details` docstring still states it "keeps the first head_lines and the last (max_lines - head_lines) lines" and does not mention the new `max(0, max_lines)` / `min(head_lines, max_lines // 2)` clamping.
**Decisions**:
Verdict(decision='tasks', tasks=['In src/mcp_workspace/github_operations/formatters.py, document the over-fetch invariant for format_issue_list: state in the docstring (and reflect in the parameter naming/signature contract) that callers must pass a list fetched with max_results + 1 items so the truncation notice can fire, and note what happens if an exactly-capped list is passed.', 'In src/mcp_workspace/server.py:825, remove the getattr(results, "totalCount", None) production fallback and access totalCount directly on the PaginatedList returned by search_issues; update the affected test doubles to expose totalCount instead of relying on plain lists.', 'In tests/github_operations/test_github_read_tools_pr_search.py, add a test that backs design note 5: use a generator-based double that counts how many items are pulled and assert that islice stops after max_results items without pulling item max_results + 1.', "In src/mcp_workspace/github_operations/ci_log_parser.py:54, update the truncate_ci_details docstring to describe the actual behavior, including the max(0, max_lines) and min(head_lines, max_lines // 2) clamping, instead of the outdated 'keeps the first head_lines and the last (max_lines - head_lines) lines' description."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-08-28
**Findings**:
I'll gather context first — loading the tools I need.`src/mcp_workspace/github_operations/formatters.py:40` — medium — `truncate_output` never clamps `max_lines`; `github_issue_view(max_lines=-1)` / `github_pr_view(max_lines=-1)` slice `lines[:-1]` (keeping all but the last line) and emit `showing -1 of N lines`, which is the misleading-cap defect this issue exists to remove. The sibling unvalidated tool parameters all gained a `max(0, ...)` clamp (`ci_log_parser.py:84`, `server.py:650`, `server.py:804`); these two `max_lines` entry points did not.

`src/mcp_workspace/git_operations/output_filtering.py:183` — medium — same missing clamp on the other `truncate_output`: `git(command=..., max_lines=-1)` reaches `lines[:-1]` and renders `[truncated: showing -1 of N lines — pass max_lines=N for the full output]` while N-1 lines were in fact returned.

`src/mcp_workspace/github_operations/formatters.py:110` — low — with `max_results=0` the over-fetched surplus item keeps `issues` non-empty, so the `No issues found.` early return is bypassed and the tool returns a body consisting only of a blank line plus `... showing 0 of 0+ results`; the notice is accurate but there is no result section for it to annotate.
**Decisions**:
Verdict(decision='tasks', tasks=["In src/mcp_workspace/github_operations/formatters.py:40, clamp max_lines in truncate_output with max(0, max_lines) (matching the sibling clamps in ci_log_parser.py:84, server.py:650, server.py:804) so negative values from github_issue_view/github_pr_view cannot slice lines[:-1] or emit a misleading 'showing -1 of N lines' notice; add a test covering max_lines=-1.", "In src/mcp_workspace/git_operations/output_filtering.py:183, apply the same max(0, max_lines) clamp in truncate_output so git(command=..., max_lines=-1) cannot return N-1 lines while reporting 'showing -1 of N lines'; add a test covering the negative max_lines path.", "In src/mcp_workspace/github_operations/formatters.py:110, handle max_results=0 so the over-fetched surplus item does not bypass the 'No issues found.' early return: evaluate emptiness against the capped result set rather than the raw over-fetched list, and add a test asserting the max_results=0 output is not a blank line followed by a bare '... showing 0 of 0+ results' notice."], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-08-28
**Findings**:
I'll start by loading the tools I need and gathering context.NO FINDINGS
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
rebase-needed
**Escalate reason**: rebase
