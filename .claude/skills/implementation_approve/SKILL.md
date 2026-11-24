---
description: Approve implementation and transition issue to PR-ready state
disable-model-invocation: true
allowed-tools:
  - mcp__mcp-workspace__github_issue_set_status
  - mcp__mcp-workspace__git
  - mcp__mcp-workspace__check_branch_status
---

# Approve Implementation

Approve the implementation and transition the issue to PR-ready state.

**Instructions:**
1. Run branch-status check:
Call `mcp__mcp-workspace__check_branch_status`.

2. If `branch-status` reports a base branch other than `main`, ask the user to confirm this is intentional before proceeding.

3. Only if the report's `Recommendations:` line contains `Ready to merge`, change the status and confirm it succeeded:
The line is comma-separated (e.g. `Recommendations: Ready to merge (squash-merge safe), ...`); `Ready to merge (squash-merge safe)` counts. The match is case-sensitive: the blocking recommendation `Not ready to merge (GitHub mergeable_state: ...)` has a lowercase `r` and must not satisfy the check.
   - Call `mcp__mcp-workspace__git` with command `status`, args `["--porcelain"]`. Any tracked or untracked change other than `uv.lock` → stop and report the uncommitted changes.
   - Call `mcp__mcp-workspace__git` with command `branch`, args `["--show-current"]`. Take the issue number from the leading digits of the branch name (`^\d+-`). No leading digits → stop and report.
   - Call `mcp__mcp-workspace__github_issue_set_status(number=<issue number>, status="status-08:ready-pr", from_status="status-07:code-review")`.
   - Result starts with `Issue #N status:` → success (a trailing `Note: issue #N is closed.` is still success). Starts with `Status of issue #N not changed:` → the guard refused (wrong current status); report it and stop. Anything else (incl. `Label … not found`, `Error:`) → failed; report the result verbatim and stop.

**Note:** If `Ready to merge` is absent, report the blockers to the user and do not set the label. If the call prompts, is refused or fails, stop and report — never fall back to Bash.

**Effect:** Changes issue status from `status-07:code-review` to `status-08:ready-pr`.

4. After the label is set, poll for the PR to be created and pass CI:
Call `mcp__mcp-workspace__check_branch_status`.
