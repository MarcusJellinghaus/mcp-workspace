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

### Step 1: `github_pr_create` uses `probe_origin_branch` — [step_1.md](./steps/step_1.md)
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy (+ lint-imports) — fix all issues
- [x] Commit message prepared

### Step 2: `_detect_from_merge_base` uses `probe_origin_branch`; delete `origin_has_branch` — [step_2.md](./steps/step_2.md)
- [ ] Implementation (tests + production code + release notes)
- [ ] Quality checks: pylint, pytest, mypy (+ lint-imports, vulture) — fix all issues
- [ ] Commit message prepared

### Step 3: Rebuild `get_full_status` on `get_working_tree_status` — [step_3.md](./steps/step_3.md)
- [ ] Implementation (parity tests + production code + release notes)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 4: `_format_dirty_tree` uses `get_working_tree_status` — [step_4.md](./steps/step_4.md)
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy (+ lint-imports) — fix all issues
- [ ] Commit message prepared

### Step 5: `commit_staged_files` precheck uses `has_staged_changes` — [step_5.md](./steps/step_5.md)
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 6: `stage_all_changes` drops its precheck — [step_6.md](./steps/step_6.md)
- [ ] Implementation (tests + production code + release notes)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 7: `commit_all_changes` precheck uses `get_working_tree_status`, fails closed — [step_7.md](./steps/step_7.md)
- [ ] Implementation (tests + production code + release notes)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 8: Delete `get_staged_changes` / `get_unstaged_changes` — [step_8.md](./steps/step_8.md)
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy (+ lint-imports, vulture) — fix all issues
- [ ] Commit message prepared

### Step 9: Rebuild `rebase_onto_branch` on `rebase_start` / `rebase_abort` — [step_9.md](./steps/step_9.md)
- [ ] Implementation (tests + production code + release notes)
- [ ] Quality checks: pylint, pytest, mypy (+ lint-imports) — fix all issues
- [ ] Commit message prepared

## Pull Request
- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
