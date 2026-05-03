---
description: Analyse GitHub issue requirements, feasibility, and implementation approaches
disable-model-invocation: true
argument-hint: "<issue-number>"
allowed-tools:
  - mcp__mcp-workspace__github_issue_view
  - mcp__mcp-workspace__git
  - mcp__mcp-workspace__read_file
  - mcp__mcp-workspace__list_directory
  - mcp__mcp-tools-py__sleep
---

# Analyse GitHub Issue

Fetch a GitHub issue and analyze its requirements, feasibility, and potential implementation approaches.

## Resolve Issue Number

The user may provide an issue number as the argument (available as `$ARGUMENTS`).
If no issue number is provided:
1. Read `.vscodeclaude_status.txt` and extract the issue number from the `Issue #NNN` line
2. If the file doesn't exist or has no issue number, ask the user

Wait one second using `mcp__mcp-tools-py__sleep` with `seconds: 1`

Fetch the issue using `mcp__mcp-workspace__github_issue_view`.

## Instructions

Analyze the issue:

Can we discuss this requirement / implementation idea and its feasibility?
Please also look at the code base to understand the context (using the different tools with access to the project directory).
Do not provide code yet!

At the end of our discussion, I want to have an even better issue description.

**Decision-awareness:**
If the issue contains a `## Decisions` section, read it carefully:
- Do NOT re-ask topics that are already decided. Focus on aspects not yet covered.
- If any existing decision seems risky or questionable given what you see in the code, briefly note the concern — but don't block on it.

**Constraints identification:**
During the discussion, actively identify constraints and rationale — the "why" behind decisions, non-obvious gotchas, things that downstream steps (`/create_plan`, `/implement`) need to know. These will be captured in the issue via `/issue_update`.

**Base Branch Handling:**
If the issue contains a `### Base Branch` section:
- Display the specified base branch prominently
- Verify the branch exists using `mcp__mcp-workspace__git` with command `"ls_remote"` and args `["--heads", "origin", "<branch-name>"]`
- If the branch does NOT exist, show a clear warning:
  "⚠️ Warning: Base branch 'X' does not exist on remote. Branch creation will fail."
- Continue with the analysis (non-blocking error)

**Focus on:**
- Understanding the problem/feature request
- Technical feasibility
- Potential implementation approaches
- Questions that need clarification
- Impact on existing code

**Note:** This skill has `disable-model-invocation` — it can only be run by the user typing `/issue_analyse`.
