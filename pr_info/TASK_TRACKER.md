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

<!-- Tasks populated from pr_info/steps/ by prepare_task_tracker -->

### Step 1: Combined linked-branch / closing-PR GraphQL query ([step_1.md](./steps/step_1.md))
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Add `LINKED_VIA_PR` status ([step_2.md](./steps/step_2.md))
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: Resolve the closing-PR fallback in `_collect_linked_branch_status` ([step_3.md](./steps/step_3.md))
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: Render `LINKED_VIA_PR` and PR-sourced `MISMATCH` ([step_4.md](./steps/step_4.md))
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: Update the `check_branch_status` skill's follow-up-action table ([step_5.md](./steps/step_5.md))
- [ ] Implementation (documentation-only change)
- [ ] Commit message prepared

## Pull Request

- [ ] Review full diff against summary.md for consistency
- [ ] Write PR title and description
- [ ] Create pull request
