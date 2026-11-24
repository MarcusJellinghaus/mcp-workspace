---
description: Return issue to plan-ready status for re-implementation after major review issues
disable-model-invocation: true
allowed-tools:
  - mcp__mcp-workspace__github_issue_set_status
  - mcp__mcp-workspace__git
---

# Return to plan-ready after major review issues

Transitions the issue back to `plan-ready` status for re-implementation when code review identifies major issues that cannot be fixed with minor changes.

## When to Use

| Situation | Action |
|-----------|--------|
| Minor fixes | Fix directly, re-run `/implementation_review` or `/implementation_review_supervisor` |
| **Major issues** | **This command** (after `/implementation_new_tasks` + `/commit_push`) |
| Approved | `/implementation_approve` |

## Prerequisites

- New implementation steps created (`/implementation_new_tasks`)
- Changes committed and pushed (`/commit_push`)

## Instructions

1. Call `mcp__mcp-workspace__git` with command `status`, args `["--porcelain"]`. Any tracked or untracked change other than `uv.lock` → stop and report the uncommitted changes.
2. Call `mcp__mcp-workspace__git` with command `branch`, args `["--show-current"]`. Take the issue number from the leading digits of the branch name (`^\d+-`). No leading digits → stop and report.
3. Call `mcp__mcp-workspace__github_issue_set_status(number=<issue number>, status="status-05:plan-ready", from_status="status-07:code-review")`.
4. Confirm the status change was successful:
   - Result starts with `Issue #N status:` → success (a trailing `Note: issue #N is closed.` is still success).
   - Result starts with `Status of issue #N not changed:` → the guard refused (wrong current status); report it and stop.
   - Anything else (incl. `Label … not found`, `Error:`) → failed; report the result verbatim and stop.

If the call prompts, is refused or fails, stop and report — never fall back to Bash.

## Next Steps

Run `mcp-coder implement` to process the new steps, then `/implementation_review` or `/implementation_review_supervisor`.
