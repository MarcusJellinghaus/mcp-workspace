# Step 7 — Docs and `.claude/` config

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 7** exactly as described
> in `pr_info/steps/step_7.md`. Steps 1–6 are done. This step changes only
> documentation and config. Run pylint, pytest (`-n auto`) and mypy via the MCP
> tools to confirm that nothing broke, then make exactly one commit.

## WHERE / WHAT

- **`SECURITY.md`**
  - `:47`: replace "Issue tools refuse `status-*` labels." with
    "General issue tools refuse `status-*` labels. Only `github_issue_set_status`
    changes them, and only to a label that already exists in the target repository."
  - `:66`: replace the Scope bullet with
    "changing an issue's status label through any tool other than
    `github_issue_set_status`, or promoting an issue without being trusted".
  - Add nothing else.
- **`README.md`**
  - Tools table (near `:387`): add a `github_issue_set_status` row with an
    example prompt, e.g. "Move issue 42 to status-05:plan-ready".
  - `github_label_list` row and description: mention the 24 h shared label
    cache, the `Label cache last updated …` footer and `refresh_labels`.
  - "Cross-Repo GitHub Access" (`:619-625`): add status changes to the list of
    writable actions. Replace the `:625` bullet with one saying that general
    tools reject `status-*` and that `github_issue_set_status` changes status
    on any configured repo, workspace or reference.
  - Add one sentence: a status change can start workflow automation in the target repository.
  - Add a short section for the tool covering its parameters, full-label-name
    validation, the `from_status` guard, PR rejection, closed issues, the
    label cache and the coordinator issue-cache update.
- **`tests/LLM_Test.md`**
  - `:177` and `:199`: expect an error naming `github_issue_set_status`. In
    `:199`, drop the "own checkout" wording.
  - Test 4.1, before the close step:
    - `github_label_list(search="status-")` → status labels plus a footer
    - `github_issue_set_status(number=<N>, status="2")` → `Label "2" not found` with the list and footer
    - `github_issue_set_status(number=<N>, status="<a status label>")` → old `<none>` → new, `Labels:`
    - the same call again → "already has status … nothing changed"
    - `github_issue_set_status(number=<N>, status="<another>", from_status="<wrong one>")` → no change, reports the actual status
    - `github_issue_set_status(number=<a PR number>, status=...)` → "is a pull request"
    - finally remove the status label: none of the tools can, so note that the
      test issue keeps it and is closed
  - Test 4.2: one cross-repo `github_issue_set_status(..., reference_name=<name>)` step.
- **`.claude/CLAUDE.md`**
  - Tool table: add the row `| Set issue workflow status | \`mcp__mcp-workspace__github_issue_set_status\` |`
    after "Edit GitHub issue".
  - Rewrite the "Status labels" rule: "use `mcp__mcp-workspace__github_issue_set_status`
    to change issue workflow status (works for reference projects too). Skills
    that still call `mcp-coder gh-tool set-status` may keep using it. Never use
    raw `gh issue edit` with label flags."
  - Keep `mcp-coder gh-tool set-status <label>` in the approved Bash list.
- **`.claude/settings.local.json`**: add `"mcp__mcp-workspace__github_issue_set_status"`
  to the allow list next to `"mcp__mcp-workspace__github_label_list"` (`:78`).
  Keep the JSON valid.

## HOW

Edit text in place with `mcp__mcp-workspace__edit_file`. No code changes.

## ALGORITHM / DATA

None.

## Note

Both `.claude/` changes must be synced back to mcp-coder after merge. The next
Shared Config Sync must not overwrite them first. This is out of scope for this
commit, and the PR description should mention it.
