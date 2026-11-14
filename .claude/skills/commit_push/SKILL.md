---
description: Format code, review changes, commit, and push to remote
disable-model-invocation: true
allowed-tools:
  - mcp__mcp-workspace__git
  - mcp__mcp-workspace__git_commit
  - mcp__mcp-workspace__git_push
  - mcp__mcp-tools-py__run_format_code
  - mcp__mcp-workspace__read_file
  - mcp__mcp-workspace__list_directory
  - mcp__mcp-workspace__search_files
---

# Commit and Push Changes

Follow this process to commit and push your changes:

## 1. Format Code
Use `mcp__mcp-tools-py__run_format_code` to format all code with the project's configured formatter.

## 2. Review Changes
Use `mcp__mcp-workspace__git` with command `"status"` to check working directory state.
Use `mcp__mcp-workspace__git` with command `"diff"` to review the changes.

## 3. Commit
Call `mcp__mcp-workspace__git_commit` with `message` and `paths` built from `git status`:
- Include modified, new and deleted files, and both the old and the new path of a rename
  (`git_commit` commits only the given paths).
- Exclude any files that shouldn't be committed.
- If no paths remain, skip the commit and go to step 4.

Use a clear, conventional commit message:
- Use format: `type(scope): description`
- Types: feat, fix, docs, style, refactor, test, chore
- Keep summary under 50 characters
- **No Claude Code footer or attribution in commit message**

If the result starts with `Nothing to commit`, go to step 4 (earlier commits may be unpushed).
If it starts with `Error:`, report it and stop — do not push.

## 4. Push
Call `mcp__mcp-workspace__git_push` (no arguments).

If it refuses (e.g. on the default branch), report it and stop. If step 3 made a commit, state
that the commit exists locally and is unpushed.
