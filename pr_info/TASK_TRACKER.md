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

### Step 1: Drop the local/remote dedupe; score every ref in one loop

Detail: [step_1.md](./steps/step_1.md)

- [x] Implementation: create `tests/git_operations/test_parent_branch_detection_git.py` with the two real-git tests, then delete `checked_branch_names` in `detect_parent_branch_via_merge_base` and merge the two scoring loops into one candidate list plus one scoring loop
- [x] Quality checks: pylint, pytest (fast subset + `markers=["git_integration"]`), mypy — fix all issues
- [x] Commit message prepared (text drafted and used for commit d2470a8; `pr_info/.commit_message.txt` is gitignored and rejected by the MCP workspace tools, so the file itself cannot be written)

### Step 2: Return `None` when the current branch is the default branch

Detail: [step_2.md](./steps/step_2.md)

- [ ] Implementation: add `test_returns_none_on_the_default_branch`, then add the default-branch guard after `default_branch` is resolved and update the docstring `Returns:` block
- [ ] Quality checks: pylint, pytest (fast subset + `markers=["git_integration"]`), mypy — fix all issues
- [ ] Commit message prepared

### Step 3: Minimum distance per branch name, and `None` on an unresolved tie

Detail: [step_3.md](./steps/step_3.md)

- [ ] Implementation: add the two tie tests, then replace `candidates_passing` with `best: dict[str, int]`, replace the sort-based winner selection with the three selection rules, and finalize the docstring `Returns:` block
- [ ] Quality checks: pylint, pytest (fast subset + `markers=["git_integration"]`), mypy — fix all issues
- [ ] Commit message prepared

### Step 4: Remove the `needs_rebase` self-comparison short-circuit

Detail: [step_4.md](./steps/step_4.md)

- [ ] Implementation: add the two `TestNeedsRebase` cases, then delete the `current_branch == target_branch` short-circuit in `needs_rebase` and move its up-to-date outcome into the `rev_parse` `GitCommandError` branch
- [ ] Quality checks: pylint, pytest (fast subset + `markers=["git_integration"]`), mypy — fix all issues
- [ ] Commit message prepared

### Step 5: Say `Pull origin/main` when the current branch is the default branch

Detail: [step_5.md](./steps/step_5.md)

- [ ] Implementation: add the recommendation test and the end-to-end `test_on_default_branch_recommends_pull`, then plumb `is_default_branch` through `report_data` and switch the wording in `_generate_recommendations`
- [ ] Quality checks: pylint, pytest (fast subset + `markers=["git_integration"]`), mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: verify all steps implemented, check for regressions and leftover defects
- [ ] PR summary prepared
