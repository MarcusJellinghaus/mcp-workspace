# review-plan review log 1

## Round 1 — 2026-08-28
**Findings**:
I'll gather context first: knowledge base, the issue tree, and the plan files.`pr_info/steps/step_3.md:76` — medium — live test never asserts returned items carry the anchor label, so a `label:` qualifier that GitHub demotes to free text (this issue's exact silent-failure mode) can still pass; assert every result line contains the label, not just that the anchor number appears.
`pr_info/steps/step_2.md:95` — medium — the `if p` empty-query filter (qualifier-only search) is behavior introduced in step 2 with no mocked test in step 2's own commit; its only exercise is the step 3 live test, which the standard `-m "not ... github_integration ..."` run excludes.
`pr_info/steps/step_3.md:87` — medium — anchor is taken from the newest open issues, whose `status-NN:` labels this repo's own automation churns; GitHub search-index lag on a just-created or just-relabelled issue makes "anchor number in result" intermittently false in CI.
`pr_info/steps/step_1.md:83` — low — rationale for keeping the `startswith("(")` filter is wrong: `format_search_results` emits its truncation line as `... N total results`, not `(...)`, and `github_search` caps `items` at `max_results` before formatting, so that branch never fires; the filter is dead once the footer is removed.
`pr_info/steps/step_2.md:97` — low — `state` is interpolated unvalidated into `is:{state}`; `state="all"` (valid vocabulary in the sibling `github_issue_list` tool) now produces an API error, with no test pinning that behavior and no docstring note.
`pr_info/steps/summary.md:112` — low — step 3 is a test-only commit tightly coupled to the behavior introduced in step 2; planning principles favour merging intertwined steps unless the split buys independent verification.
**Decisions**:
Verdict(decision='tasks', tasks=["In pr_info/steps/step_3.md:76, strengthen the live search test: assert that every returned result line contains the anchor issue's `label:` value, not merely that the anchor issue number appears — so a qualifier GitHub silently demotes to free text fails the test.", 'In pr_info/steps/step_2.md:95, add a mocked unit test in step 2\'s own commit covering the `if p` empty-query filter (qualifier-only search, e.g. label/state qualifiers with no free-text terms), so the behavior is verified in the default `-m "not ... github_integration ..."` run rather than only by the step 3 live test.', 'In pr_info/steps/step_2.md:97, define and pin the accepted `state` vocabulary before interpolating it into `is:{state}`: handle or explicitly reject `state="all"` (the sibling `github_issue_list` accepts it), document the valid values in the docstring, and add a test asserting the chosen behavior for `all` and for an invalid value.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-08-28
**Findings**:
I'll gather context first — knowledge base, the issue graph, and the plan files.`pr_info/steps/step_3.md:97` — high — anchor label is taken as `anchor["labels"][0]` from the newest open issues, which in this repo is typically a churning `status-NN:` label; GitHub's search index lags label mutations, so both "anchor number present" and "every result line contains the anchor label" can false-fail — prefer a stable label (skip `status-`-prefixed ones) or pick the oldest open labelled issue
`pr_info/steps/step_3.md:96` — medium — `IssueManager.list_issues` is wrapped in `_handle_github_errors(default_return=[])`, so an auth/permission failure returns `[]` and the test skips as "no open labelled issues"; the sole live verification this issue requires can silently no-op — distinguish an empty repo from a swallowed API error
`pr_info/steps/step_3.md:95` — medium — anchor discovery constructs `IssueManager(project_dir=repo_root)` directly, which raises `ValueError` when the checkout is not a git repo or has no GitHub origin; the plan's only skip guards are token and labelled-issues, so the test errors instead of skipping in such environments
`pr_info/steps/step_1.md:83` — medium — rationale for keeping the `startswith("(")` filter in `test_github_search_issue_vs_pr_indicator` is factually wrong: `format_search_results` emits its truncation line as `... N total results` (not `(...)`) and `github_search` caps `items` at `max_results` before formatting, so that branch cannot fire; the filter becomes dead code created by this change
`pr_info/steps/step_2.md:34` — low — `query=""` becomes a supported, tested path (and the shape step 3's live test sends) but no docstring change is planned for the `query` parameter, which still reads "Search query text" with no indication a qualifier-only search is valid
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_3.md:97, stop using `anchor["labels"][0]` from the newest open issues: select a stable anchor label by skipping `status-`-prefixed (automation-churned) labels and picking the oldest open labelled issue, so neither the anchor-number assertion nor the per-line label assertion depends on a just-mutated label that GitHub\'s search index has not yet caught up with.', "In pr_info/steps/step_3.md:96, distinguish a genuinely empty repo from a swallowed API error during anchor discovery: since `IssueManager.list_issues` is wrapped in `_handle_github_errors(default_return=[])`, an auth/permission failure currently makes the sole live test skip as 'no open labelled issues' — detect the error case and fail (or skip with an explicit auth-failure reason) instead of silently no-opping.", 'In pr_info/steps/step_3.md:95, guard the `IssueManager(project_dir=repo_root)` construction: it raises `ValueError` when the checkout is not a git repo or has no GitHub origin, so add a skip guard for that case alongside the existing token and labelled-issues guards, ensuring the test skips rather than errors in such environments.'], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-08-28
**Findings**:
I'll start by loading the tools I need and gathering context.`pr_info/steps/step_3.md:130` — high — the "generous `max_results` (100) so the anchor is not pushed past the cutoff" rationale contradicts the round-2 oldest-anchor rule: `github_search(query="", state="open", labels=[anchor_label], max_results=100)` sends no `sort`/`order`, so GitHub returns best-match/newest-first; once the anchor label has more than 100 open issues+PRs the *oldest* anchor falls outside the cap and `assert anchor number in result` red-fails CI with no bug present — pass `sort="created", order="asc"` (both are already supported kwargs) so the oldest match is deterministically first.

`pr_info/steps/step_3.md:91` — medium — "do not pass `max_results` to `list_issues`" makes anchor discovery page through every open issue and PR in the repo (`repo.get_issues()`, 30 per page, PRs filtered client-side after fetch) on every live run, spending many API calls before the one search the test actually verifies.

`pr_info/steps/step_1.md:83` — medium — the instruction to keep the `startswith("(")` filter in `test_github_search_issue_vs_pr_indicator` rests on a false claim: `format_search_results` emits its truncation line as `\n... N total results...`, not `(...)`, and `github_search` slices `items` to `max_results` before formatting so that branch cannot fire — the filter becomes dead code created by this change (reported in rounds 1 and 2, not addressed).
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_3.md:130, make the anchor search deterministic for the oldest-anchor rule: pass `sort="created", order="asc"` to `github_search(query="", state="open", labels=[anchor_label], max_results=100)` so the oldest matching issue is returned first and cannot be pushed past the 100-result cap by GitHub\'s default best-match/newest-first ordering, and update the surrounding rationale text that currently justifies the cap alone.'], escalate_reason=None)
**Changes**:
applied

## Round 4 — 2026-08-28
**Findings**:
I'll gather context first — knowledge base, the issue tree, and the plan files.`pr_info/steps/step_3.md:140` — high — the only live test sends `query=""` (qualifier-only), so no live call ever exercises free text combined with a state qualifier — the exact shape of the issue's repro 3 (`github_search(query="status", state="open")` → "No results found."); that combination is pinned only by a mocked exact-string assertion, which the plan itself argues cannot prove GitHub honors the syntax. Add a free-text term (e.g. a word from the anchor issue's title) to the live search, or a second live assertion, so the reported failing call shape is covered against the real API.
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_3.md:140, extend the live coverage so the issue\'s repro 3 shape (free text plus a state qualifier) hits the real API: add a second live assertion (or extend the existing one) that calls `github_search` with a non-empty `query` — e.g. a distinctive word taken from the anchor issue\'s title — together with `state="open"` and the anchor label, and assert the anchor issue number appears in the results; keep the existing qualifier-only (`query=""`) live assertion as well.'], escalate_reason=None)
**Changes**:
applied

## Round 5 — 2026-08-28
**Findings**:
I'll gather context first — knowledge base, the issue tree, and the plan files.`pr_info/steps/step_1.md:83` — medium — "Leave `test_github_search_issue_vs_pr_indicator` alone" rests on a false claim: `format_search_results` (`src/mcp_workspace/github_operations/formatters.py:203-224`) emits its truncation line as `... N total results. Showing first N.`, not `(... more)`, and `github_search` already slices `items` to `max_results` before formatting, so the `startswith("(")` line filter cannot fire once the footer is removed — it becomes dead code introduced by this change (raised in rounds 1–3, still unaddressed).
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
