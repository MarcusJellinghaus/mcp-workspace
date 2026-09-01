# review-plan review log 1

## Round 1 — 2026-09-01
**Findings**:
I'll gather context first.`pr_info/steps/step_3.md:52` — high — Claim "both already name every tool this step stops enumerating in prose" is false for README: the per-tool table at `README.md:223-229` ends at `github_search`, so after steps 2+3 the names `github_label_list`, `github_issue_create`, `github_issue_edit` and `github_issue_comment` appear nowhere in README (verified: their only occurrences today are lines 35, 383, 455, all removed by this plan). Plan must add the four missing table rows or keep one naming mention.

`pr_info/steps/summary.md:99` — medium — "Unchanged on purpose: `README.md:223-229` (per-tool table)" rests on the same incorrect premise; if the table gains the four missing rows, this line and the file table at lines 90-97 need the README/step-3 entry updated.

`pr_info/steps/summary.md:74` — medium — Step 1's "no automated test" rationale is weaker than stated: `FastMCP.instructions` is a public read-only property (`mcp.server.fastmcp.FastMCP.instructions`), so a non-tautological content test (mentions reference projects, contains no `github_*` enumeration, contains no filesystem path) is one assertion and would automate three of the issue's verification bullets that the plan otherwise leaves manual-only, against the knowledge base's "No manual tests."

`pr_info/steps/step_1.md:62` — medium — Same gap at step level: "Tests: None" plus "do not reach for `mcp._mcp_server`" omits that `mcp.instructions` is public, so the step gives no automated guard that the instructions text stays free of tool names and paths.

`pr_info/steps/step_2.md:15` — low — The new `usage` sentence is still duplicated verbatim in five places (usage literal, docstring pointer, two test expectations, `README.md:383`); the plan removes the drift's cost but not the duplication the issue names as the root cause.

`pr_info/steps/step_1.md:35` — low — "Answer questions about another repo from its reference project instead of asking the user" is unconditional, but the text ships in every session including servers with zero reference projects configured; a short hedge would avoid prompting a pointless `get_reference_projects()` call.
**Decisions**:
Verdict(decision='tasks', tasks=["In pr_info/steps/step_3.md, fix the incorrect premise at line 52: add the four missing rows (github_label_list, github_issue_create, github_issue_edit, github_issue_comment) to the README per-tool table at README.md:223-229 so the tools remain named somewhere in README after steps 2+3, and update the step's claim text accordingly.", "In pr_info/steps/summary.md, update line 99 ('Unchanged on purpose: README.md:223-229') and the file table at lines 90-97 to reflect that the README per-tool table is now modified by step 3.", "In pr_info/steps/step_1.md, replace 'Tests: None' with an automated test using the public FastMCP.instructions property asserting the instructions text mentions reference projects, contains no github_* tool enumeration, and contains no filesystem path; drop the '_mcp_server' framing that implied no public accessor exists.", "In pr_info/steps/summary.md line 74, replace the 'no automated test' rationale with the step 1 instructions-content test now planned, noting which of the issue's verification bullets it automates."], escalate_reason=None)
**Changes**:
applied
