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

### Step 1: Linked Branch wording for `LINKED_VIA_PR` — [step_1.md](./steps/step_1.md)
- [ ] Implementation: tests (`OK via PR` prefix, substrings, long branch name in both formats) + `_format_linked_branch_line` change + SKILL.md row
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 2: `head_sha` on `PullRequestData` — [step_2.md](./steps/step_2.md)
- [ ] Implementation: `get_pull_request` test for `head_sha` + `PullRequestData.head_sha` field + `_pr_to_data` mapping + docstring
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 3: `PRChecksMixin.get_non_green_checks` — [step_3.md](./steps/step_3.md)
- [ ] Implementation: `tests/github_operations/test_pr_checks_mixin.py` + new `pr_checks_mixin.py` + add mixin to `PullRequestManager` bases
- [ ] Quality checks: pylint, pytest, mypy, lint-imports — fix all issues
- [ ] Commit message prepared

### Step 4: Report fields, `unstable` recommendation wording, `Non-green checks:` line — [step_4.md](./steps/step_4.md)
- [ ] Implementation: recommendation + rendering tests + report fields, `_merge_state_recommendation`, `format_check_names`, `_format_non_green_checks_line`, both formats + SKILL.md rows
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: Re-read `unstable` once, then look up checks, in `collect_branch_status` — [step_5.md](./steps/step_5.md)
- [ ] Implementation: `tests/checks/test_branch_status_unstable_recheck.py` + `_recheck_unstable` + step 9b wiring + report fields passed through (`branch_status.py` ≤ 750 lines)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request
- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
