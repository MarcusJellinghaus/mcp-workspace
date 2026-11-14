---
description: Rebase feature branch onto base branch with conflict resolution
disable-model-invocation: true
allowed-tools:
  - mcp__mcp-workspace__git
  - mcp__mcp-workspace__git_commit
  - mcp__mcp-workspace__git_push
  - mcp__mcp-workspace__git_push_force
  - "Bash(git rebase *)"
  - "Bash(git add *)"
  - "Bash(git rm *)"
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

Call `mcp__mcp-workspace__get_base_branch` to detect the correct base branch. Use the returned branch name in subsequent git commands.

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
2. Run the Branch Moved Check (below), which also captures `PRE_SHA`. If it stops: report it. Nothing to undo.
3. `git rebase origin/${BASE_BRANCH}`
4. For each conflict:
   - If file is under `pr_info/`: auto-resolve with `git checkout --theirs <file>` (keep feature branch version), then `git add <file>` — no user input needed
   - For all other files: resolve manually, preserving main's improvements; rework feature branch changes to fit
   - Verify no conflict markers remain
   - `git add <file>`
   - `git rebase --continue`
5. Run code checks: `mcp__mcp-tools-py__run_pytest_check`, `mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_mypy_check`
6. Fix any issues from merge
7. Report summary
8. Repeat the Branch Moved Check against the same `PRE_SHA`. If it stops: do not push, and print `git reset --hard <PRE_SHA>` for the human to run.
9. Push, choosing by the Branch Moved Check result:
   - `refs/remotes/origin/<branch>` absent (never pushed): `mcp__mcp-workspace__git_push`.
   - Otherwise: `mcp__mcp-workspace__git_push_force`. If it refuses with a message containing
     `needs git 2.30+` or `has no reflog`, run `git push --force-with-lease` instead.
   - Any other refusal or failure: report it and stop. This is not Abort Rule 1 — do not run
     `git rebase --abort`; the rebase has already completed.

## Branch Moved Check

**Why:** a fetch refreshes the tracking ref, which disables the lease for commits someone else pushed. `git push --force-with-lease` would then remove those commits from the remote and still succeed. The check stops the run if `origin/<branch>` has commits this checkout did not have before the rebase.

All calls go through `mcp__mcp-workspace__git`:

1. `branch` = command `"branch"`, args `["--show-current"]`
2. `PRE_SHA` = command `"rev_parse"`, args `["HEAD"]`. Capture this once, before the rebase; the repeat in workflow step 8 reuses it. Do not read `HEAD` again.
3. Command `"rev_parse"`, args `["--verify", "refs/remotes/origin/<branch>"]`
   - Error `fatal: Needed a single revision`: the ref is absent. Skip the rest of this check; workflow step 9 uses `git_push`.
   - Any other error: stop as described in the workflow step, and report it.
4. Command `"merge_base"`, args `["--is-ancestor", "refs/remotes/origin/<branch>", PRE_SHA]`
   - `"true"`: continue.
   - `"false"`: someone else pushed to the branch. Stop as described in the workflow step, and report it.
   - Error: not a pass. Stop as described in the workflow step, and report it.

Use `refs/remotes/origin/<branch>`, not the bare name: a tag named `origin/<branch>` makes the check pass wrongly.

**Abort instruction:** an error from this check is a stop, not Abort Rule 1, and the `git rebase --abort` line under Abort Rules does not apply to either stop. At the first, no rebase has started. At the second, the rebase has already completed.

**Do not work around it:** on a stop, do not fetch and push again. The next fetch only hides the foreign commit from the lease.

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
