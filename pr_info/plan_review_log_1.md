# review-plan review log 1

## Round 1 — 2026-11-09
**Findings**:
Read steps 1–7. Now reading steps 8–14 before writing the report.pr_info/steps/step_1.md:58 — high — `_strip` deletes every `description`/`title` key recursively, including keys inside `properties`. `github_issue_create`, `github_issue_edit` and `github_pr_create` have a parameter named `title` (`server.py:1379`, `:1453`, `:1988`), so that parameter's type and default drop out of the snapshot unchecked. The acceptance criterion requires parameter names, types and defaults to be pinned. Fix: strip only schema-annotation keys, never the parameter-name keys of a `properties` mapping, and add an assertion that `title` survives in `github_issue_create`'s snapshot.
pr_info/steps/step_11.md:14 — low — Says `_GROUPS` "now has all 10 register functions", but the plan defines 9 (read, write, delete, move, reference, git, github_read, github_write, checks).
pr_info/steps/step_2.md:125 — low — Step 2 declares every future `toolset` dependency in tach, then says to "drop any dependency tach reports as unused". If tach does report unused dependencies, steps 3–11 must add each one back, and none of those steps says so.
**Decisions**:
Verdict(decision='tasks', tasks=['pr_info/steps/step_1.md:58 — change `_strip` so it removes only schema-annotation `description`/`title` keys and never the parameter-name keys inside a `properties` mapping. Add an assertion that the `title` parameter, with its type and default, survives in the `github_issue_create` snapshot.', "pr_info/steps/step_11.md:14 — change the `_GROUPS` count from 10 to 9 so it matches the plan's register functions (read, write, delete, move, reference, git, github_read, github_write, checks). If the plan really means 10, name the missing one.", "pr_info/steps/step_2.md:125 — choose one approach to tach dependencies. Either declare each `toolset` dependency in the step that first uses it (steps 3–11), or keep all of them in step 2 and remove the instruction to drop dependencies tach reports as unused. Each step's tach check must pass."], escalate_reason=None)
**Changes**:
applied
