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

### Step 1: Timeout-bounded git subprocess helper — [step_1.md](./steps/step_1.md)
- [x] Implementation: tests + `git_operations/_subprocess_git.py` (`run_git_timed`, `GitOutput`) + `.importlinter` ignore line
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 2: `push_current_branch` — [step_2.md](./steps/step_2.md)
- [x] Implementation: tests + `origin_clone` / `make_clone` fixtures, `git_version` public, `_remote_tracking_reflog_exists`, `push_current_branch`
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 3: `remote_head_sha` — [step_3.md](./steps/step_3.md)
- [x] Implementation: tests + `RemoteHeadResult` (core.py) + `remote_head_sha` (remotes.py)
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 4: Guardrail queries — [step_4.md](./steps/step_4.md)
- [x] Implementation: tests + `is_valid_branch_name_strict`, `resolve_base_ref`, `resolve_commit`, `is_ancestor`, `operation_in_progress`
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 5: Branch mutations returning `GitResult` — [step_5.md](./steps/step_5.md)
- [x] Implementation: tests + `create_and_switch_branch`, `switch_branch`, `delete_local_branch_force`
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 6: Staging `list_untracked_paths`, `stage_paths` — [step_6.md](./steps/step_6.md)
- [x] Implementation: tests + `list_untracked_paths`, `stage_paths` (staging.py)
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 7: Commit reporting `committed_files`, public `format_dirty_tree` — [step_7.md](./steps/step_7.md)
- [x] Implementation: tests + `committed_files` (commits.py) + rename `_format_dirty_tree` → `format_dirty_tree`
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 8: `PullRequestManager.find_merged_pr_by_head_sha` — [step_8.md](./steps/step_8.md)
- [x] Implementation: tests + `find_merged_pr_by_head_sha` (pr_manager.py)
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 9: Tool `git_branch` (+ `git_write.py`, helpers module, lock) — [step_9.md](./steps/step_9.md)
- [x] Implementation: tests + `git_write_lock`, `toolset/git_write.py`, `toolset/_git_write_helpers.py` (`do_git_branch`, guards, `run_tool`), registration, `EXPECTED`/`ASYNC_TOOLS`, `git_branch.json` snapshot
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 10: Tool `git_branch_delete` — [step_10.md](./steps/step_10.md)
- [x] Implementation: tests + `git_branch_delete` closure, `do_git_branch_delete`, `tip_on_github`, `EXPECTED`/`ASYNC_TOOLS`, `git_branch_delete.json` snapshot
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 11: Tool `git_commit` — [step_11.md](./steps/step_11.md)
- [x] Implementation: tests + `git_commit` closure, `do_git_commit`, `format_commit_result`, `EXPECTED`/`ASYNC_TOOLS`, `git_commit.json` snapshot
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 12: Tool `git_push` — [step_12.md](./steps/step_12.md)
- [x] Implementation: tests + `git_push` closure, `guard_push_branch`, `do_git_push`, `EXPECTED`/`ASYNC_TOOLS`, `git_push.json` snapshot
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 13: Tool `git_push_force` — [step_13.md](./steps/step_13.md)
- [x] Implementation: tests + `git_push_force` closure, `EXPECTED`/`ASYNC_TOOLS`, `git_push_force.json` snapshot
- [x] Quality checks (format, pylint, pytest, mypy, lint-imports, ruff) — fix all issues
- [x] Commit message prepared

### Step 14: Docs — README, LIBRARY_USE, ARCHITECTURE, SECURITY — [step_14.md](./steps/step_14.md)
- [x] Implementation: README tool rows, `docs/LIBRARY_USE.md`, `docs/ARCHITECTURE.md`, `SECURITY.md`
- [x] Quality checks (pytest, file sizes < 750 lines) — fix all issues
- [x] Commit message prepared

### Step 15: LLM_Test section, Claude settings and CLAUDE.md — [step_15.md](./steps/step_15.md)
- [ ] Implementation: `tests/LLM_Test.md` Section 5, `.claude/settings.local.json` allowlist, `.claude/CLAUDE.md` tool table / Bash git list
- [ ] Quality checks (settings JSON valid, pytest) — fix all issues
- [ ] Commit message prepared

## Pull Request
- [ ] PR review: review the full branch diff against `main`, address findings
- [ ] PR summary prepared
