---
description: Approve issue to transition to next workflow status
disable-model-invocation: true
argument-hint: "<issue-number> [--repo owner/repo]"
allowed-tools:
  - mcp__mcp-workspace__github_issue_view
  - mcp__mcp-workspace__github_issue_comment
  - "Bash(gh issue view *)"
  - "Bash(MSYS_NO_PATHCONV=1 gh issue comment *)"
  - mcp__mcp-tools-py__sleep
  - mcp__mcp-workspace__read_file
---

# Approve Issue

Approve the current issue to transition it to the next status in the workflow.

## Resolve Issue Number

The user may provide an issue number as the argument (available as `$ARGUMENTS`).
If no issue number is provided:
1. Check if the issue number is known from prior `/issue_analyse` or `/issue_create` in this conversation
2. Read `.vscodeclaude_status.txt` and extract the issue number from the `Issue #NNN` line
3. If still unknown, ask the user

## Cross-Repo Issues

If a `--repo owner/repo` flag was given, append it to every `gh` command below. When that
repo is a configured reference project — match `owner/repo` against the `url` of each entry
`get_reference_projects()` returns — pass that entry's `name` as `reference_name` to the MCP
tools: `mcp__mcp-workspace__github_issue_view` and `mcp__mcp-workspace__github_issue_comment`
both reach it. Otherwise fall back to the `gh ... --repo owner/repo` Bash forms.

## Instructions

1. Fetch the issue to confirm it exists:
   Call `mcp__mcp-workspace__github_issue_view` with the issue number (or with `reference_name` for a cross-repo issue).

   Note its current status label — step 5 compares against it.

2. Validate that the issue is ready for approval:
   - Issue has been analyzed/discussed
   - Requirements are clear
   - No blocking questions remain

   If any check fails, stop and report — do not approve.

3. Comment `/approve` on the issue:

```python
mcp__mcp-workspace__github_issue_comment(number=<issue_number>, body="/approve")
```

For a cross-repo issue (`--repo owner/repo`) that *is* a configured reference project, pass
its `reference_name`:

```python
mcp__mcp-workspace__github_issue_comment(number=<issue_number>, body="/approve", reference_name=<name>)
```

For any other repo, use Bash instead — the MCP tool only reaches the workspace repository
and its configured reference projects. `MSYS_NO_PATHCONV=1` prevents Windows Git Bash from
rewriting the leading `/` and is needed only for this Bash form:

```bash
MSYS_NO_PATHCONV=1 gh issue comment <issue_number> --body "/approve" --repo owner/repo
```

This triggers the GitHub Action to promote the issue status (e.g., `status-01:created` → `status-02:awaiting-planning`).

4. **Wait 5 seconds** — call `mcp__mcp-tools-py__sleep` with `sleep_seconds: 5` — to give the
   GitHub Action time to apply the label transition.

5. **Confirm the transition landed.** Re-fetch the issue and compare its status label against
   what you saw in step 1. The comment in step 3 only *requests* the transition; the Action
   performs it, and it can be slow or fail.

   If the label has not changed, report the issue as still sitting at its old status.

6. Report the issue number, the status transition (from → to, or "unchanged"), and the
   assignee.

**Note:** This skill has `disable-model-invocation` — it can only be run by the user typing `/issue_approve`. If you need this skill as a follow-up, tell the user: "Please run `/issue_approve` to proceed."
