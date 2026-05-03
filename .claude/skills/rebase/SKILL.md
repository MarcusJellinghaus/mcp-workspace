---
description: Rebase feature branch onto base branch with conflict resolution
disable-model-invocation: true
allowed-tools:
  - mcp__mcp-workspace__git
  - "Bash(git rebase *)"
  - "Bash(git add *)"
  - "Bash(git rm *)"
  - "Bash(git commit *)"
  - "Bash(git checkout --ours *)"
  - "Bash(git checkout --theirs *)"
  - "Bash(git remote get-url *)"
  - "Bash(git restore *)"
  - "Bash(git stash *)"
  - "Bash(git push --force-with-lease *)"
  - mcp__mcp-tools-py__run_format_code
  - mcp__mcp-workspace__get_base_branch
  - mcp__mcp-tools-py__run_pylint_check
  - mcp__mcp-tools-py__run_pytest_check
  - mcp__mcp-tools-py__run_mypy_check
  - mcp__mcp-workspace__read_file
  - mcp__mcp-workspace__save_file
  - mcp__mcp-workspace__edit_file
  - mcp__mcp-workspace__list_directory
  - mcp__mcp-workspace__get_reference_projects
  - mcp__mcp-workspace__list_reference_directory
  - mcp__mcp-workspace__read_reference_file
  - mcp__mcp-workspace__append_file
  - mcp__mcp-workspace__delete_this_file
  - mcp__mcp-workspace__move_file
---

# Rebase Branch onto Base Branch

## First Step

Call `mcp__mcp-workspace__git` with command `"status"` before doing anything else.

Rebase the current feature branch onto its base branch and resolve conflicts.

**Core philosophy:** Main is the source of truth. The feature branch adapts to main. For source code conflicts, preserve main's improvements and rework the feature branch code to fit.

**Note on `--ours`/`--theirs` during rebase:** `--ours` = main (the branch being rebased onto), `--theirs` = feature branch commits being replayed.

If the rebase becomes complex, suggest switching to cherry-picking as an alternative approach.

## Determine Base Branch

First, detect the correct base branch using `mcp__mcp-workspace__get_base_branch`.

## Base Branch Confirmation

If the base branch is not `main` or `master`, ask the user to confirm before proceeding. Display the detected base branch and wait for explicit approval.

## Pre-flight Checks (Abort if any fail)

1. Working directory is clean (no uncommitted changes)
2. Not already in rebase/merge state
3. Not on main/master branch
4. Remote origin exists
5. `pr_info/` does not exist on the base branch — if it does, abort with error: `"pr_info/ exists on <BASE_BRANCH>. This folder should only exist on feature branches. Check your branch setup."`

## Workflow

1. Call `mcp__mcp-workspace__git` with command `"fetch"` and args `["origin"]`
2. `git rebase origin/${BASE_BRANCH}`
3. For each conflict:
   - If file is under `pr_info/`: auto-resolve with `git checkout --theirs <file>` (keep feature branch version), then `git add <file>` — no user input needed
   - For all other files: resolve manually, preserving main's improvements; rework feature branch changes to fit
   - Verify no conflict markers remain
   - `git add <file>`
   - `git rebase --continue`
4. Run code checks: `mcp__mcp-tools-py__run_pytest_check`, `mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_mypy_check`
5. Fix any issues from merge
6. Report summary and ask for user confirmation
7. `git push --force-with-lease`

## Conflict Resolution Strategies

| File Type | Strategy |
|-----------|----------|
| `pr_info/` files | Auto-resolve with `--theirs` (keep feature branch version) |
| Code files (`.py`, `.js`, etc.) | Keep both sides, merge imports |
| Test files | Keep all tests from both sides |
| Config files | Merge additively, prefer HEAD for same keys |
| Lockfiles (`*-lock.json`, `*.lock`) | Accept theirs (`--theirs`), notify user to regenerate after rebase |

## Abort Rules (in priority order)

1. Any unexpected error - abort, report full error
2. Binary file conflict - abort, cannot auto-resolve
3. Conflict markers remain after resolution - abort
4. Same file conflicts 3+ times - abort
5. Code quality fails after 2 fix attempts - abort
6. Any other unexpected situation - abort, suggest manual intervention

On abort: run `git rebase --abort`, report which rule triggered, suggest next steps.
