# Step 15 — LLM_Test section, Claude settings and CLAUDE.md

## LLM prompt

> Read `pr_info/steps/summary.md` and this file. Implement step 15 only (no code). This step is
> deliberately last: it removes Bash git commands from `.claude/CLAUDE.md`, which is only safe
> once the tools exist. Make exactly one commit.

## WHERE / WHAT

### `tests/LLM_Test.md` — new section after Section 4

`## Section 5: Git write tools (MUTATING — opt-in, local only)` — no push (remote branches
created here could not be deleted by any tool).

1. `git(command="branch", args=["--show-current"])` — note the branch as `<orig>`
2. `git_commit(message="x")` — expect an error saying to pass exactly one of `paths` / `all`
3. `git_branch(name="-x", create=True)` — expect `Error: invalid branch name`
4. `git_branch(name="llm-test-git-write", create=True)` — expect `Created llm-test-git-write from HEAD (<sha>)`
5. `save_file(".scratch/llm_git_write.txt", "x")`
6. `git_commit(message="LLM test commit", paths=[".scratch/llm_git_write.txt"])` — expect
   `Committed <sha> on llm-test-git-write (1 files)` and the file listed
7. `git_branch(name="<orig>")` — expect `Switched to <orig>`
8. `git_branch_delete(name="llm-test-git-write")` — expect `Error: refusing to delete llm-test-git-write: tip <sha> is not on GitHub`
9. `git_branch_delete(name="<orig>")` — expect an error: the current branch is refused
10. Cleanup (manual, Bash): `git branch -D llm-test-git-write`

### `.claude/settings.local.json`

Add to `permissions.allow`:
`mcp__mcp-workspace__git_branch`, `mcp__mcp-workspace__git_commit`, `mcp__mcp-workspace__git_push`.
Do **not** add `git_branch_delete` or `git_push_force` (they always prompt).

### `.claude/CLAUDE.md`

- Tool-mapping table, after `Git (read-only)`:
  `| Create / switch branch | mcp__mcp-workspace__git_branch |`,
  `| Delete local branch | mcp__mcp-workspace__git_branch_delete |`,
  `| Commit | mcp__mcp-workspace__git_commit |`,
  `| Push | mcp__mcp-workspace__git_push |`,
  `| Force push after rebase | mcp__mcp-workspace__git_push_force |`.
- "Allowed commands via Bash tool" code block: `git commit / add / rebase / push / checkout -b / branch`
  → `git add / rebase` (rebase conflict resolution: `git add <file>` + `git rebase --continue`).
- "Before every commit": "run `run_format_code`, then commit with `git_commit`".

## HOW / ALGORITHM / DATA

Documentation and config only. Verify `.claude/settings.local.json` is still valid JSON by
reading it back.

## Commit

`chore(claude): allow git write tools and document them`
