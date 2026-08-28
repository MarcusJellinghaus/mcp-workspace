# review-plan review log 1

## Round 1 — 2026-08-28
**Findings**:
I'll start by loading the tools I need and gathering context.`pr_info/steps/step_1.md:83` — high — Docstring guidance is limited to adding a `reference_name` entry to each `Args:` block; `github_search`'s summary line "Search GitHub issues and pull requests in this repository" and the body note "Automatically scoped to current repository" (`server.py:746`, `:748`) directly contradict the new parameter and are not updated by step 1, step 3, or any other step. This text is the MCP tool description callers read.

`pr_info/steps/step_3.md:22` — medium — Step 3 updates only the `usage` return value of `get_reference_projects()`, but that function's own docstring (`server_reference_tools.py:47`, "Use the returned project names with `list_reference_directory()` and `read_reference_file()`") enumerates the same tool list and is the tool description surfaced to callers; it is left stale in the very function the step edits.

`pr_info/steps/step_3.md:42` — medium — The three README touch points omit `README.md:378`, which hardcodes an example `usage` string (`"Use these 3 projects with list_reference_directory() and read_reference_file()"`). It sits inside the `#### Get Reference Projects` subsection and is the same string step 3 changes.

`pr_info/steps/summary.md:134` — medium — The plan ships an unresolved open question rather than a decision: `.claude/skills/issue_approve/SKILL.md:27-29` will still instruct agents that `github_issue_view` "only reaches the current repository" and to fall back to `gh issue view --repo` for cross-repo reads — the exact fallback the issue's Evidence section exists to remove. The implementer is left with no instruction.

`pr_info/steps/step_1.md:168` — low — `test_reference_read_does_not_clone` patches `mcp_workspace.server_reference_tools.ensure_available`, but the planned `get_reference_repo_url()` never references it, so the test cannot fail for any implementation matching the plan's ALGORITHM; it guards only a hypothetical future rewrite.
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_1.md, extend the docstring guidance beyond the Args: block: instruct the implementer to update github_search\'s summary line at server.py:746 ("Search GitHub issues and pull requests in this repository") and the body note at server.py:748 ("Automatically scoped to current repository") so the MCP tool description reflects the new reference_name parameter and cross-repo capability.', 'In pr_info/steps/step_3.md, add the get_reference_projects() docstring at server_reference_tools.py:47 to the edit list, so the sentence "Use the returned project names with `list_reference_directory()` and `read_reference_file()`" is updated with the same tool list as the usage return value being changed in that step.', 'In pr_info/steps/step_3.md:42, add README.md:378 to the README touch points — the hardcoded example usage string "Use these 3 projects with list_reference_directory() and read_reference_file()" in the #### Get Reference Projects subsection must be updated to match the new usage string.', 'Resolve the open question at pr_info/steps/summary.md:134 with a concrete instruction rather than leaving it to the implementer: add a step that updates .claude/skills/issue_approve/SKILL.md:27-29 to remove the claim that github_issue_view "only reaches the current repository" and to drop the `gh issue view --repo` fallback, since removing that fallback is the issue\'s stated goal.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-08-28
**Findings**:
I'll gather context first — knowledge base, the issue tree, and the plan files.`pr_info/steps/step_2.md:32` — medium — Decision 4's diagnosability is applied only at the two `_get_repository()` sites (`github_pr_view`, `github_search`); `github_issue_view`/`github_issue_list` against a reference project on a non-GitHub or misconfigured host return `"Error: Issue #N not found"` (because `get_issue` is wrapped by `_handle_github_errors(default_return=create_empty_issue_data())`), with no API base URL and no hint the host is wrong. A full fix would need manager-layer changes the issue forbids, so the plan should state this limitation explicitly instead of implying decision 4 is fully covered.

`pr_info/steps/step_3.md:165` — low — The DONE WHEN criterion `grep -r "only reaches the current repository"` returns nothing is unsatisfiable as written: the string still exists in `pr_info/steps/step_3.md:102` (the quoted "before" text) and in `pr_info/plan_review_log_1.md:11`, so the implementer either fails the gate or edits plan files to pass it; scope the grep to `src/`, `README.md`, `.claude/` and `tests/`.

`pr_info/steps/step_1.md:168` — low — All five tests assert constructor kwargs or error strings; nothing asserts observable cross-repo behaviour, e.g. that `github_search(reference_name="sibling")` issues `repo:owner/sibling ...` via `manager._github_client.search_issues`. `_configure_manager` already sets `_get_repository -> MagicMock(full_name="owner/sibling")`, so one query assertion would cover summary §5's github_search claim at near-zero cost.

`pr_info/steps/step_3.md:57` — low — Step 3 updates only `README.md:378` inside the `#### Get Reference Projects` example, leaving `README.md:369` and `:377` stating `projects` is a "List of project names" / `["docs", "examples", "utils"]`, while the tool returns `{"name": ..., "url": ...}` dicts. The `url` field is what tells a caller whether a project supports the new GitHub reads, so the stale lines are load-bearing for this feature and sit in the block being edited.
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_2.md near line 32, add an explicit limitation note to Decision 4: state that the API-base-URL diagnostic applies only to the two `_get_repository()` call sites (`github_pr_view`, `github_search`), and that `github_issue_view`/`github_issue_list` still return the generic `"Error: Issue #N not found"` for a misconfigured or non-GitHub host because `get_issue` is wrapped by `_handle_github_errors(default_return=create_empty_issue_data())`; note that fixing this would require manager-layer changes the issue excludes.', 'In pr_info/steps/step_3.md:165, scope the DONE WHEN grep so it is satisfiable: restrict `grep -r "only reaches the current repository"` to `src/`, `README.md`, `.claude/` and `tests/` so the quoted "before" text in step_3.md:102 and the occurrence in pr_info/plan_review_log_1.md:11 do not fail the gate.', 'In pr_info/steps/step_1.md near line 168, add one behavioural test assertion alongside the kwargs/error-string tests: assert that `github_search(reference_name="sibling")` passes a query beginning with `repo:owner/sibling` to `manager._github_client.search_issues`, using the existing `_configure_manager` mock that sets `_get_repository -> MagicMock(full_name="owner/sibling")`.', 'In pr_info/steps/step_3.md:57, extend the `#### Get Reference Projects` README edits to also cover README.md:369 and README.md:377, which still describe `projects` as a "List of project names" with example `["docs", "examples", "utils"]`; update them to the actual `{"name": ..., "url": ...}` dict shape and mention that `url` indicates whether a project supports the new GitHub reads.'], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-08-28
**Findings**:
I'll gather context first: knowledge base, the issue tree, and the plan files.`NO FINDINGS`
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
