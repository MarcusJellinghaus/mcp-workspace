# Summary: `github_issue_view` optionally reports linked branches (#303)

## Goal

Let an agent ask "which branches are linked to issue N?" through the MCP surface.
`github_issue_view` gains an opt-in `include_linked_branches` flag. When set, the output
gains a `Linked branches: ...` line directly under the State line.

## Architectural / design changes

- **No new modules or classes.** The existing `LinkedBranchesMixin.get_linked_branches_or_none()`
  (via `IssueBranchManager`) is wired into the existing tool.
- **Formatter stays pure.** `format_issue_view` takes two new keyword-only arguments and makes no
  API calls. The server fetches the data and passes it in.
  - `linked_branches: list[str] | None` — the lookup result (`None` = lookup failed).
  - `include_linked_branches: bool` — whether the line is rendered at all. A separate flag is
    needed because a bare `None` cannot mean both "not requested" and "lookup failed".
- **Lookup failure never fails the view.** A new private server helper `_linked_branches()`
  builds an `IssueBranchManager` for the same target as the view (`project_dir`, or `repo_url`
  of the reference project) and absorbs every failure into `None`, mirroring
  `_collect_linked_branch_status` in `checks/branch_status.py`. The try/except is local, so the
  tool's outer `except` never turns a lookup failure into an `Error:` result.
- **Cost:** flag off costs nothing extra. Flag on adds two requests (REST `get_repo` on the fresh
  manager plus GraphQL). `IssueManager`'s cached repo is private and is not reused.
- **Not-found issue:** the lookup is skipped; the existing error is returned unchanged.

## Output

Line 4, joined to the State line with `\n`, so it survives any `max_lines >= 4`:

```
# #1176: Adopt deptry

State: open | Labels: none | Assignees: none
Linked branches: 1176-adopt-deptry-for-dependency-hygiene
```

Forms: `Linked branches: 12-a, 12-b` · `Linked branches: none` ·
`Linked branches: unknown (lookup failed)`. No line when the flag is off.

## Files modified

| File | Change |
|---|---|
| `src/mcp_workspace/github_operations/formatters.py` | `format_issue_view` gains keyword-only `linked_branches`, `include_linked_branches` |
| `src/mcp_workspace/server.py` | `github_issue_view` gains `include_linked_branches`; new helper `_linked_branches` |
| `tests/github_operations/test_formatters.py` | Line forms, position, flag off, `max_lines=4` |
| `tests/github_operations/test_github_read_tools_issues.py` | Flag off/on, three failure paths, not-found skip |
| `tests/github_operations/test_github_read_tools_reference.py` | Reference project uses `repo_url` |

No files or folders are created outside `pr_info/steps/`.

## Steps

1. [step_1.md](./step_1.md) — formatter renders the linked-branches line.
2. [step_2.md](./step_2.md) — `github_issue_view` flag and lookup helper.
