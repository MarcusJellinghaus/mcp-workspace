---
description: Format code, review changes, commit, and push to remote
disable-model-invocation: true
allowed-tools:
  - mcp__mcp-workspace__git
  - "Bash(git add *)"
  - "Bash(git commit *)"
  - "Bash(git push *)"
  - mcp__mcp-tools-py__run_format_code
  - mcp__mcp-workspace__read_file
  - mcp__mcp-workspace__list_directory
  - mcp__mcp-workspace__search_files
---

# Commit and Push Changes

Follow this process to commit and push your changes:

## 1. Format Code
Use `mcp__mcp-tools-py__run_format_code` to format all code (black + isort).

## 2. Review Changes
Use `mcp__mcp-workspace__git` with command `"status"` to check working directory state.
Use `mcp__mcp-workspace__git` with command `"diff"` to review the changes.

## 3. Stage Changes
Stage all relevant changes (exclude any files that shouldn't be committed).

## 4. Commit
Create a commit with a clear, conventional commit message:
- Use format: `type(scope): description`
- Types: feat, fix, docs, style, refactor, test, chore
- Keep summary under 50 characters
- **No Claude Code footer or attribution in commit message**

## 5. Push
```bash
git push
```

If the branch doesn't exist on remote yet:
```bash
git push -u origin HEAD
```
