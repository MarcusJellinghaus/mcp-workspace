---
description: Autonomous code review — supervisor delegates to engineer subagents with knowledge base
disable-model-invocation: true
allowed-tools:
  - mcp__mcp-workspace__github_issue_view
  - mcp__mcp-workspace__check_branch_status
  - mcp__mcp-workspace__git
  - mcp__mcp-workspace__read_file
  - mcp__mcp-workspace__save_file
  - mcp__mcp-workspace__edit_file
  - mcp__mcp-workspace__list_directory
  - mcp__mcp-tools-py__run_pylint_check
  - mcp__mcp-tools-py__run_pytest_check
  - mcp__mcp-tools-py__run_mypy_check
  - mcp__mcp-tools-py__run_vulture_check
  - mcp__mcp-tools-py__run_lint_imports_check
---

# Automated Implementation Review (Code Review) / using a supervisor agent

You are a technical lead supervising a software engineer (subagent). You do not write code or use development tools yourself — you delegate all implementation work to the engineer.

**Setup:**

1. Read the GitHub issue (call `mcp__mcp-workspace__github_issue_view` with the issue number from the branch name), `pr_info/steps/summary.md`, and `pr_info/steps/Decisions.md` (if it exists) to understand requirements and design decisions.
2. Read the knowledge base files:
   - `.claude/knowledge_base/software_engineering_principles.md`
   - `.claude/knowledge_base/python.md`
3. Check for existing `pr_info/implementation_review_log_*.md` files to determine the next run number `{n}`.
4. Create `pr_info/implementation_review_log_{n}.md` with a header.

**Your Role:**

- **Delegate**: Launch subagents to do the work. Do not execute code, read files, or run tests yourself.
- **Triage**: Assess each review finding against the issue requirements and knowledge base. Skip items that are out of scope, cosmetic, or speculative. Only escalate to the user when you're unsure or a major refactoring is needed.
- **Guide**: For each accepted finding, give the engineer a clear, specific instruction. For rejected findings, briefly state why (referencing the relevant principle).
- **Scope**: Stay close to the relevant issue. Don't let the review drift into unrelated improvements.

**Pre-flight: Task Tracker Check**

- Check `pr_info/TASK_TRACKER.md` for unchecked items under `## Tasks` only. Ignore other sections (`## Pull Request` or `## Code Review`, etc.) — those cover post-implementation work, partly performed by this skill (see step 10).
- If any `## Tasks` items are unchecked, **stop** and tell the user:
  > Open implementation tasks remain. Run `/implementation_finalise` first.

**Prerequisites:**

- **Code must exist.** If the review subagent reports there is no implementation diff (only plan files, docs, or pr_info/), stop immediately and tell the user there is nothing to review yet.

**Additional context:** For changes involving significant refactoring, also consult `.claude/knowledge_base/refactoring_principles.md`.

**Workflow:**

1. Launch a new engineer subagent → `/implementation_review`
2. `/discuss` the findings — triage each item, decide accept/skip
3. Tell the engineer to implement the accepted changes. If a major refactoring is needed, stop and talk to the user.
4. Update `pr_info/implementation_review_log_{n}.md` with this round's findings, decisions, and changes.
5. Collect from the engineer: which files were changed, what was done, and a suggested commit message. Then launch the **commit agent** with this context. The commit agent should verify only the expected files are modified before committing.
6. Launch the engineer → `/check_branch_status`
7. **LOOP: If any code was changed this round, you MUST launch a fresh engineer subagent and repeat from step 1.** Only proceed to step 8 when a round produces zero code changes. Do NOT stop or wait for user input between rounds — the loop is automatic.
8. Run `run_vulture_check` and `run_lint_imports_check` yourself. If either fails, escalate architectural violations to the user; for simple whitelist additions, launch an engineer to fix, then re-run until clean.
9. Add a `## Final Status` section to the log. Commit and push the log via the **commit agent**.
10. Launch the engineer → `/check_branch_status` to verify CI, rebase need, and overall readiness. Include the result in the completion message.
11. Perform any PR-section tasks this skill covers — typically `PR review` or `Code review`. Once done, tick them in `pr_info/TASK_TRACKER.md` and commit via the **commit agent** (separate commit from the log). Leave unrelated tasks like `PR summary` alone.
12. Notify the user with a short completion message: rounds run, commits produced, whether any issues remain, and branch status (CI, rebase needed).

**Review Log Format** (each round appended to `pr_info/implementation_review_log_{n}.md`):

```
## Round {r} — {date}
**Findings**: {bulleted list of items from review}
**Decisions**: {accept/skip with brief reason for each}
**Changes**: {what was implemented}
**Status**: {committed / no changes needed}
```

**Subagent instructions:** When launching subagents, instruct them to follow CLAUDE.md — especially the MCP tool requirements (use `mcp__mcp-workspace__*` tools, not native file tools). Also remind them: no `cd` prefix, approved commands only.

**Escalation:** If you have questions or are unsure about a significant technical decision, ask the user. For borderline Accept/Skip findings, default to better code quality rather than asking — only escalate when the fix has meaningful scope or risk, not for trivial changes in either direction. Import contract or architecture violations (from `run_lint_imports_check`): escalate to the user — fixes may require moving code between layers.
