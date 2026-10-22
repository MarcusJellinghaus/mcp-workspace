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

### Step 1: `get_head_commit_info` git helper
See [step_1.md](./steps/step_1.md)

- [x] Implementation: `TestGetHeadCommitInfo` tests + `get_head_commit_info` in `commits.py`, exported from `git_operations/__init__.py`
- [x] Quality checks: pylint, pytest (`-n auto -k "not github_search_live"`), mypy, tach, lint-imports — fix all issues
- [x] Commit message prepared

### Step 2: Return the comment, new report fields, header rendering
See [step_2.md](./steps/step_2.md)

- [x] Implementation: `find_latest_marked_comment` returns `CommentData`; `BranchStatusReport` fields replace `last_automated_note`; `_format_utc` + `_format_last_marked_comment_lines` renderer; update formatter and branch status tests
- [x] Quality checks: pylint, pytest (`-n auto -k "not github_search_live"`), mypy, tach, lint-imports — fix all issues
- [x] Commit message prepared

### Step 3: Collect timestamps, HEAD and the stale verdict
See [step_3.md](./steps/step_3.md)

- [ ] Implementation: `_marked_comment_context` helper + wiring in `collect_branch_status`; `tach.toml` `checks → utils` dependency; collection tests (stale, current, tie, HEAD unavailable, unparseable `created_at`, HEAD not looked up without comment)
- [ ] Quality checks: pylint, pytest (`-n auto -k "not github_search_live"`), mypy, tach, lint-imports; `branch_status.py` ≤ 750 lines — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main`, address findings
- [ ] PR summary prepared
