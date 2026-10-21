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

### Step 1: Parser on markdown-it-py (+ dependency, startup assertion)
See [step_1.md](./steps/step_1.md)

- [x] Implementation: tests (`test_parse_base_branch_markdown.py`, startup assertion) + `parse_base_branch` rewrite, `markdown-it-py` dependency
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Shared message helper `format_malformed_base_branch`
See [step_2.md](./steps/step_2.md)

- [x] Implementation: tests (helper sentence, fenced heading accepted on write) + helper in `issues/base.py`, `_check_base_branch` uses it
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: `IssueData.base_branch_error` + log-once in the manager
See [step_3.md](./steps/step_3.md)

- [x] Implementation: tests (`test_manager_base_branch.py`, conftest reset fixture) + `base_branch_error` field, `_parse_base_branch_fields` in `get_issue`/`list_issues`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: Public `origin_has_branch`
See [step_4.md](./steps/step_4.md)

- [x] Implementation: tests (`test_base_branch_git.py`) + replace `_origin_still_has_branch`, inline catch in `_detect_from_merge_base`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 5: Server helper `_resolve_base_branch` + `get_base_branch`
See [step_5.md](./steps/step_5.md)

- [x] Implementation: tests (`test_server_get_base_branch.py`) + `_resolve_base_branch`, `get_base_branch` rewrite
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 6: Remove `issue_manager` from `detect_base_branch` (no double fetch)
See [step_6.md](./steps/step_6.md)

- [x] Implementation: tests (`TestDetectFromIssue` updated) + drop parameter/fetch path, update `collect_branch_status` call
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 7: `github_pr_create` default base follows the issue
See [step_7.md](./steps/step_7.md)

- [x] Implementation: tests (`test_github_pr_create_base.py`, `TestGithubPrCreate` patches) + resolve omitted `base` via `_resolve_base_branch`, verify with `origin_has_branch`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 8: Tri-state `rebase_needed`; rebase recommendation names the detected base
See [step_8.md](./steps/step_8.md)

- [x] Implementation: tests (`test_branch_status_base_branch.py`, recommendations tests) + `Optional[bool]` rebase state, UNKNOWN rendering, `Rebase onto origin/<base>`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 9: Malformed Base Branch in `check_branch_status` (+ Review Gate)
See [step_9.md](./steps/step_9.md)

- [x] Implementation: tests (`test_branch_status_base_branch.py`, `test_branch_status_review_gate.py`) + malformed state in `collect_branch_status`, fix recommendation, `BLOCKED (base branch)` gate
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

## Pull Request

- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
