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

## Round 2 — 2026-09-01
**Findings**:
I'll gather context first.`pr_info/steps/step_3.md:51` — high — The "four missing rows" set is incomplete. `search_reference_files` and `git` appear in `README.md` **only** at line 383 (the quoted `usage` string step 2 rewrites), and `github_pr_create` appears **only** at line 460 (the bullet step 3 rewrites); verified by grep. After steps 2+3 all three vanish from README entirely — the same regression round 1 flagged for the four GitHub tools, unfixed for these three.

`pr_info/steps/summary.md:40` — medium — Restates the same incomplete premise ("gains the four rows it is missing ... which otherwise appear in `README.md` only in the passages steps 2 and 3 remove"); the row set and this sentence both need `search_reference_files`, `git` and `github_pr_create` accounted for.

`pr_info/steps/step_1.md:84` — low — `assert "\\" not in text and "/" not in text` is a brittle proxy for "no filesystem path": it also rejects legitimate slashes (`read/write`, `owner/repo`, any URL), so harmless rewording of the instructions breaks the test for a reason unrelated to the constraint.

`pr_info/steps/step_2.md:15` — low — "used verbatim in all four places" contradicts the docstring variant at lines 56-57, which ends with a period while the other three do not.

`pr_info/steps/step_2.md:48` — low — The docstring summary stays "Get available reference project names" while the same edit corrects `projects` from "List of project names" to `{"name", "url"}` dicts; the summary line carries the identical inaccuracy the issue asks to fix.
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_3.md, extend the README per-tool table row set beyond the four GitHub tools: also add rows for search_reference_files, git and github_pr_create, which otherwise disappear from README once step 2 rewrites the usage string at README.md:383 and step 3 rewrites the bullet at README.md:460.', "In pr_info/steps/summary.md line 40, correct the premise sentence to cover all seven tools (the four GitHub write/label tools plus search_reference_files, git and github_pr_create) rather than only 'the four rows it is missing'."], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-09-01
**Findings**:
I'll gather context first.`pr_info/steps/step_3.md:20` — high — The `README.md:35` replacement ("the GitHub issue, pull request, search and label tools accept `reference_name`") is false as a category claim: `github_pr_create` is a pull-request tool with no `reference_name` parameter (`src/mcp_workspace/server.py:1464`), and the same step adds a `github_pr_create` row to the tool table. The replacement must scope the claim to the read tools plus issue writes, e.g. "the GitHub issue, pull request, search and label read tools accept `reference_name`; issues can also be created, edited and commented on."

`pr_info/steps/step_3.md:26` — high — The `README.md:455` replacement opens "The GitHub tools take an optional `reference_name`", which contradicts the bullet the same step writes at `README.md:460` ("Any GitHub tool without a `reference_name` parameter targets the workspace repository") and is wrong for `github_pr_create`; the section documenting exactly this boundary would state the rule incorrectly in its first sentence.
**Decisions**:
Verdict(decision='tasks', tasks=["In pr_info/steps/step_3.md line 20, correct the README.md:35 replacement text so it does not claim all GitHub pull-request tools accept reference_name: scope it to the read tools plus issue writes, e.g. 'the GitHub issue, pull request, search and label read tools accept reference_name; issues can also be created, edited and commented on.'", "In pr_info/steps/step_3.md line 26, fix the README.md:455 replacement's opening sentence so it does not state that all GitHub tools take an optional reference_name — github_pr_create has no such parameter — and make it consistent with the bullet the same step writes at README.md:460."], escalate_reason=None)
**Changes**:
applied
