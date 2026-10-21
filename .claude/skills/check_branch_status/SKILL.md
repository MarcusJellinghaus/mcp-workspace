---
description: Check branch readiness including CI, rebase needs, tasks, and labels
allowed-tools:
  - mcp__mcp-workspace__check_branch_status
---

Call `mcp__mcp-workspace__check_branch_status`.

# Check Branch Status

Checks CI status, rebase needs, task completion, and GitHub labels. Reports actionable recommendations.

## Follow-Up Actions

| Status | Action |
|--------|--------|
| CI failures | Fix the issues shown in CI error details |
| Rebase needed | `/rebase` |
| Tasks incomplete | Complete remaining tasks manually |
| Linked branch `MISMATCH` / `NOT_LINKED` / `AMBIGUOUS` / `UNKNOWN` | Relink the branch in the issue's Development panel, or open a PR on this branch with `Closes #N` in its body |
| Linked branch `OK via PR` | Already satisfies the check — no action needed |
| CI green + tasks done | `/commit_push` or create PR |
| Ready to merge | Create PR or merge via GitHub |
