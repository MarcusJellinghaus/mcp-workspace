---
description: Approve implementation plan and transition to plan-ready status
disable-model-invocation: true
allowed-tools:
  - mcp__mcp-workspace__github_issue_set_status
  - mcp__mcp-workspace__git
---

# Approve Implementation Plan

Approve the implementation plan and transition the issue to implementation-ready state.

**Instructions:**
1. Change the status:
   - Call `mcp__mcp-workspace__git` with command `status`, args `["--porcelain"]`. Any tracked or untracked change other than `uv.lock` → stop and report the uncommitted changes.
   - Call `mcp__mcp-workspace__git` with command `branch`, args `["--show-current"]`. Take the issue number from the leading digits of the branch name (`^\d+-`). No leading digits → stop and report.
   - Call `mcp__mcp-workspace__github_issue_set_status(number=<issue number>, status="status-05:plan-ready", from_status="status-04:plan-review")`.

2. Confirm the status change was successful:
   - Result starts with `Issue #N status:` → success (a trailing `Note: issue #N is closed.` is still success).
   - Result starts with `Status of issue #N not changed:` → the guard refused (wrong current status); report it and stop.
   - Anything else (incl. `Label … not found`, `Error:`) → failed; report the result verbatim and stop.

   If the call prompts, is refused or fails, stop and report — never fall back to Bash.

**Effect:** Changes issue status from `status-04:plan-review` to `status-05:plan-ready`.
