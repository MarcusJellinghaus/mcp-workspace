# Task Status Tracker

## Instructions for LLM

This tracks **Feature Implementation** consisting of multiple **Tasks**.

**Summary:** See [summary.md](./steps/summary.md) for implementation overview.

**How to update tasks:**
1. Change [ ] to [x] when implementation step is fully complete (code + checks pass)
2. Change [x] to [ ] if task needs to be reopened
3. Add brief notes in the linked detail files if needed
4. Keep it simple - just GitHub-style checkboxes

**Task format:**
- [x] = Task complete (code + all checks pass)
- [ ] = Task not complete
- Each task links to a detail file in steps/ folder

---

## Tasks

### Step 1: Foundations — `GitResult`, `CommitResult` extension, env, runner, helpers
See [step_1.md](./steps/step_1.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `pull`
See [step_2.md](./steps/step_2.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: `commit_paths`
See [step_3.md](./steps/step_3.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: `unstage_paths`
See [step_4.md](./steps/step_4.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 5: `get_working_tree_status`
See [step_5.md](./steps/step_5.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 6: `probe_rebase_conflicts` (+ conflict-repo test builder)
See [step_6.md](./steps/step_6.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 7: `probe_origin_branch` + `origin_has_branch` wrapper
See [step_7.md](./steps/step_7.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 8: `list_remote_branches`
See [step_8.md](./steps/step_8.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 9: `detect_base_branch_with_source` + `BaseBranchSource`
See [step_9.md](./steps/step_9.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 10: `clone_repo` relaxation + credential scrubbing
See [step_10.md](./steps/step_10.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 11: A4 docstrings
See [step_11.md](./steps/step_11.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 12: Rebase flow — `is_rebase_in_progress`, `rebase_start/continue/skip/abort`
See [step_12.md](./steps/step_12.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 13: `reset_hard`
See [step_13.md](./steps/step_13.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 14: `list_unmerged_paths`
See [step_14.md](./steps/step_14.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 15: `get_conflict_blob_info` + `read_conflict_stage`
See [step_15.md](./steps/step_15.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 16: `resolve_take_theirs_or_remove`
See [step_16.md](./steps/step_16.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 17: `has_staged_changes`
See [step_17.md](./steps/step_17.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 18: `list_tree`
See [step_18.md](./steps/step_18.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 19: Release notes
See [step_19.md](./steps/step_19.md)
- [x] Implementation (`docs/release-notes.md`)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

## Pull Request
- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared (from `docs/release-notes.md`)
