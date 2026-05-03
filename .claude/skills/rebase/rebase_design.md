# Rebase Slash Command - Design Document

Note: The `.txt` suffix prevents Claude Code from treating this file as a slash command.

## Overview

This document captures design decisions for the `/rebase` slash command.

## Permissions

The slash command requires two sets of permissions in `allowed-tools`:

### 1. Rebase-Specific Permissions (documented here)

These are the additional git permissions needed specifically for rebase operations:

```
# Status and investigation (MCP tools for read-only operations)
mcp__mcp-workspace__git  # read-only: status, log, fetch, branch, ls-files, rev-parse

# Rebasing
Bash(git rebase:*)

# Staging and committing
Bash(git add:*)
Bash(git rm:*)
Bash(git commit:*)

# Conflict resolution helpers
Bash(git checkout --ours:*)
Bash(git checkout --theirs:*)
Bash(git restore:*)
Bash(git stash:*)

# Pushing
Bash(git push --force-with-lease:*)
```

### 2. General Permissions (not documented here)

Include all permissions from `.claude/settings.local.json`. These provide standard MCP tool access (filesystem, tools-py, etc.) needed for conflict resolution and code quality checks.

**Maintenance note:** When `.claude/settings.local.json` changes, update the slash command's `allowed-tools` to include the new general permissions.

## Key Design Decisions

### 1. Permissions Scoped to Command
Permissions are defined in the command's `allowed-tools` frontmatter rather than global settings. This limits git write operations to only when the rebase command is active.

### 2. Pre-flight Checks
Rebase should not start if:
- Uncommitted changes exist (risk of losing work)
- Already in rebase/merge state (conflicting operations)
- On main/master branch (should only rebase feature branches)
- No remote origin (required for `git fetch origin`, `git rebase origin/main`, and `git push`)

### 3. Conflict Resolution Philosophy
- **Additive merging**: Keep code from both sides when possible
- **Conversation files are disposable**: Generated artifacts, safe to delete
- **Conservative on unknowns**: Abort rather than guess

### 4. Abort Priority
Critical failures (unexpected errors, binary conflicts) take priority over threshold-based failures (repeated conflicts, quality check failures).

### 5. User Confirmation Before Push
Force-push is destructive. Always show summary and get confirmation.

## Future Considerations

- `mcp-coder rebase` command for automated workflows
- Configurable resolution strategies per project
- Integration with PR conflict detection
