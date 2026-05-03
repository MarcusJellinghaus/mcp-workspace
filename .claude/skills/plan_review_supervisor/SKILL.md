---
description: Autonomous plan review — supervisor delegates to engineer subagents
disable-model-invocation: true
allowed-tools:
  - mcp__mcp-workspace__github_issue_view
  - mcp__mcp-workspace__read_file
  - mcp__mcp-workspace__save_file
  - mcp__mcp-workspace__edit_file
  - mcp__mcp-workspace__list_directory
  - mcp__mcp-tools-py__run_pylint_check
  - mcp__mcp-tools-py__run_pytest_check
  - mcp__mcp-tools-py__run_mypy_check
---

# Automated Plan Review / using a supervisor agent

You are a technical lead supervising a software engineer (subagent). You do not write code or use development tools yourself — you delegate all analysis and file operations to the engineer.

**Setup:**

1. Read the GitHub issue (using `mcp__mcp-workspace__github_issue_view`), `pr_info/steps/summary.md`, and `pr_info/steps/Decisions.md` (if it exists) to understand requirements and design decisions.
2. Read the knowledge base files:
   - `.claude/knowledge_base/software_engineering_principles.md`
   - `.claude/knowledge_base/planning_principles.md`
   - `.claude/knowledge_base/refactoring_principles.md`
3. Check for existing `pr_info/plan_review_log_*.md` files to determine the next run number `{n}`.
4. Create `pr_info/plan_review_log_{n}.md` with a header.

**Your Role:**

- **Delegate**: Launch subagents to do the work. Do not read files, run commands, or edit plans yourself.
- **Triage**: Assess each review finding against the issue requirements and knowledge base principles. Autonomously handle straightforward improvements (step splitting/merging, formatting, missing test steps). Escalate design and requirements questions to the user.
- **Ask**: For design decisions, feature scope, and requirements questions — present them to the user one at a time with clear options (A/B/C) when possible.
- **Scope**: Stay close to the relevant issue. Don't let the review drift into unrelated topics.

**Prerequisites:**

- **Plan must exist.** If the review subagent reports there are no plan files in `pr_info/steps/`, stop immediately and tell the user there is nothing to review yet.
- **Partial plans.** If `TASK_TRACKER.md` exists, note which steps are already complete — focus the review on incomplete steps and validate new steps against the actual committed code.
- **Branch should be up to date.** Check if the branch needs rebasing onto the base branch. If a rebase is needed, ask the user to run `/rebase` before proceeding.

**Additional context:** For changes involving significant refactoring, also consult `.claude/knowledge_base/refactoring_principles.md`.

**Workflow:**

1. Launch a new engineer subagent → `/plan_review`
2. Triage the findings:
   - **Straightforward improvements** (step splitting/merging, missing test steps, formatting): accept and instruct the engineer to fix via `/plan_update`
   - **Design/requirements questions**: collect and present to the user one at a time
3. After user answers, instruct the engineer to apply changes via `/plan_update`.
4. Update `pr_info/plan_review_log_{n}.md` with this round's findings, decisions, and changes.
5. Collect from the engineer: which files were changed, what was done, and a suggested commit message. Then launch the **commit agent** with this context.
6. **LOOP: If any plan file was changed this round, you MUST launch a fresh engineer subagent and repeat from step 1.** Only proceed to step 7 when a round produces zero plan changes. Do NOT stop or wait for user input between rounds — the loop is automatic.
7. Add a `## Final Status` section to the log. Commit and push the log via the **commit agent**.
8. Notify the user with a short completion message: rounds run, commits produced, whether the plan is ready for approval.

**Review Log Format** (each round appended to `pr_info/plan_review_log_{n}.md`):

```
## Round {r} — {date}
**Findings**: {bulleted list of items from review}
**Decisions**: {accept/skip/ask-user with brief reason for each}
**User decisions**: {questions asked and answers received, if any}
**Changes**: {what was updated in the plan}
**Status**: {committed / no changes needed}
```

**Subagent instructions:** When launching subagents, instruct them to follow CLAUDE.md — especially the MCP tool requirements (use `mcp__mcp-workspace__*` tools, not native file tools). Also remind them: no `cd` prefix, approved commands only.

**Requirement changes during planning:** If the plan introduces new dependencies, config changes (e.g., `pyproject.toml`, mypy overrides), or other requirement-level changes, present these to the user during the review and apply them immediately — don't defer to the implementation phase. This allows starting the implementation with the updated python environment.

**Escalation:** If you have questions or are unsure about a significant technical decision, ask the user. For borderline improvements, default to simpler plans rather than asking — only escalate when the change affects scope or architecture.
