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

### Step 1: `_push_retry.py` — 500 matcher and retry loop ([step_1.md](./steps/step_1.md))

- [x] Implementation: tests in `tests/git_operations/test_push_retry.py` + `src/mcp_workspace/git_operations/_push_retry.py` (`_match_500`, `retry_500`, `_RETRY_WAITS`)
- [x] Quality checks (pylint, pytest `-n auto`, mypy, format) — fix all issues
- [x] Commit message prepared

### Step 2: Retry GitPython pushes — `git_push`, `push_branch`, `delete_branch` ([step_2.md](./steps/step_2.md))

- [ ] Implementation: call-site tests appended to `test_push_retry.py` + wrap `repo.git.push` calls in `remotes.py` / `branches.py` with `retry_500`, docstring lines, remove step comments
- [ ] Quality checks (pylint, pytest `-n auto`, mypy, format) — fix all issues
- [ ] Commit message prepared

### Step 3: Retry `push_current_branch` (MCP `git_push` / `git_push_force`) ([step_3.md](./steps/step_3.md))

- [ ] Implementation: tests appended to `test_push_retry.py` + `retry_500(run_git_timed, ...)` in `push_current_branch`, docstring line
- [ ] Quality checks (pylint, pytest `-n auto`, mypy, format, `check_file_size(max_lines=750)` gate on `remotes.py`) — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
