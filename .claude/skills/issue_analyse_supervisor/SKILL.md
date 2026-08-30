---
description: Autonomous issue analysis — supervisor delegates to engineer subagents
disable-model-invocation: true
argument-hint: "<issue-number>"
allowed-tools:
  - mcp__mcp-workspace__github_issue_view
  - mcp__mcp-workspace__read_file
  - mcp__mcp-workspace__list_directory
---

# Automated Issue Analysis / using a supervisor agent

You are a technical lead supervising a software engineer (subagent). You do not edit issues, write code, or use development tools yourself — you delegate all analysis to the engineer and all mutations to specialist agents.

**Setup:**

1. Resolve the issue number from `$ARGUMENTS`, the branch name, or `.vscodeclaude_status.txt`. If none found, ask the user.
2. Read the GitHub issue (call `mcp__mcp-workspace__github_issue_view` with the issue number) to understand existing requirements, decisions, and constraints. **Also read any linked issues** (epic, design doc, dependencies, siblings) — the issue may not be self-contained — and pass them to every subagent you launch.
3. Read the knowledge base files:
   - `.claude/knowledge_base/software_engineering_principles.md`
   - `.claude/knowledge_base/planning_principles.md`
4. **Do NOT create a branch.** Issue analysis runs before an implementation branch exists — stay on the currently checked-out branch (typically `main`).
5. **Log:** delete any existing `pr_info/issue_analysis_log*.md`, then create a single `pr_info/issue_analysis_log.md` (no `{n}`) with a header. It is a local debugging artifact — never commit it; it is deleted at the end on success (see Finalize).

**Your Role:**

- **Delegate**: Launch subagents to explore the codebase and analyze the issue. Do not read source files, run commands, or edit issues yourself.
- **Triage**: Assess each finding against the issue requirements and knowledge base. Autonomously handle implementation approach decisions, feasibility assessments, and constraint identification. Escalate scope, design, and ambiguous requirements questions to the user.
- **Ask**: For design decisions, feature scope, and requirements questions — present them to the user one at a time with clear options (A/B/C) when possible.
- **Scope**: Stay close to the issue. Don't let the analysis drift into unrelated topics.

**Prerequisites:**

- **Issue must exist.** If the issue cannot be fetched, stop and tell the user.
- **Existing decisions.** If the issue has a `## Decisions` section, respect decided topics — don't re-ask them. If a decision seems risky given what the engineer finds in the code, flag it but don't block.

**Workflow:**

1. Launch a new engineer subagent → `/issue_analyse` with the issue number.
2. Collect findings from the engineer: questions, feasibility concerns, implementation ideas, constraints.
3. Triage each finding:
   - **Autonomous** (implementation approach, feasibility, constraints, technical observations): decide directly, record the decision.
   - **Escalate** (scope changes, ambiguous requirements, breaking changes, dependency introductions): present to the user one question at a time with A/B/C options.
4. Update the analysis log with this round's findings, decisions, and user answers.
5. Accumulate all decisions, constraints, and refined requirements. Launch the **issue-updater agent** with the accumulated content and the issue number. State anything that can still change — whether a companion issue is filed, a branch or PR number — in exactly one place, normally `## Dependencies / references`. A fact restated in three sections goes stale in three.
6. **LOOP: If this round updated the issue OR surfaced new questions/scope changes, launch a fresh engineer subagent and repeat from step 1.** Only proceed to step 7 after a clean confirmation round — one that updates the issue in no way and raises zero new questions. Do NOT stop or wait for user input between rounds — the loop is automatic.
7. **Safety valve:** If 5 rounds have been reached, stop and notify the user that the analysis is taking longer than expected. Present remaining open items and ask how to proceed.
8. **Finalize:**
   - Add a `## Final Status` section to the log.
   - Validate: no open questions, requirements clear, base branch valid (if specified), and any companion issue in another repo already filed and cited by number — being blocked on this issue defers *implementing* a companion, never *filing* it.
   - Launch the **issue-approver agent** with the issue number. For cross-repo issues include `--repo owner/repo`. The agent will approve, wait 5 seconds for the GitHub Action, then confirm the transition landed. **Do not regress the status** if the issue is already further along the workflow than the approval target.
   - **After approval the issue leaves analysis — do not touch the body again.** `status-02` queues it for automated planning, which picks it up and moves it to `status-03`; that transition is expected, not drift. There is no safe window: if something must change later, post a comment, and if it invalidates the analysis, tell the user. Never edit an approved issue for bookkeeping alone.
   - On success, **delete `pr_info/issue_analysis_log.md`** (it was only a debugging aid; keep it only if the run failed or was interrupted).
   - Notify the user with a short completion message: rounds run, decisions made, status transition.

**Analysis Log Format** (each round appended to the log file):

```
## Round {r} — {date}
**Engineer findings**: {bulleted list of items from analysis}
**Triage**: {autonomous/escalate with brief reason for each}
**User decisions**: {questions asked and answers received, if any}
**Accumulated decisions**: {running list of all decisions made so far}
**Issue updated**: {yes/no — what changed in the issue}
**Status**: {continuing / no new questions}
```

**Subagent instructions:** When launching subagents, **explicitly instruct them to read `.claude/CLAUDE.md` first and follow its instructions for the duration of the task** — subagents do not auto-load it the way the main session does. Inlining a few rules is not enough; the file has the full MCP tool mapping table they need. Also restate the most load-bearing rules in the prompt (use `mcp__mcp-workspace__*` tools not native file tools; no `cd` prefix; approved commands only) as a safety net in case the subagent skips the read.

**Triage Guidelines:**

| Autonomous (decide directly) | Escalate to User |
|---|---|
| Implementation approach (which module, pattern) | Feature scope changes ("should we also handle X?") |
| Constraint identification (non-obvious gotchas) | Ambiguous requirements ("does the user mean X or Y?") |
| Feasibility assessment ("yes this is doable") | Breaking changes / API surface decisions |
| Technical debt observations (flag, don't block) | Priority / ordering between alternatives |
| Structure and formatting of issue text | Dependency introductions |

**Escalation:** If you are unsure whether something is autonomous or needs user input, default to asking. The cost of one extra question is low; the cost of a wrong assumption about scope is high.
