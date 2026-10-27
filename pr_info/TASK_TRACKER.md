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

### Step 1: Unique temp file names in `_save_cache_file` — [step_1.md](./steps/step_1.md)

- [ ] Implementation: tests (temp naming, cleanup, replace retry) + `_save_cache_file` with `mkstemp` and one `os.replace` retry
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 2: Fetch additional issues only when needed; keep session issues on full refresh — [step_2.md](./steps/step_2.md)

- [ ] Implementation: tests (fetch rule, full-refresh put-back) + `_needs_fetch`, `_fetch_additional_issues` returning fetched keys, steps 5b/5c in `get_all_cached_issues`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 3: Save fetched additional issues on duplicate-protection and list-failure paths — [step_3.md](./steps/step_3.md)

- [ ] Implementation: tests (reload-merge save, timestamps untouched, list outage) + `_save_fetched_issues` wired into both early-return paths
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 4: Per-process `Repository` raw-data cache — [step_4.md](./steps/step_4.md)

- [ ] Implementation: scratch probe (then delete `.scratch/`), tests + `_token_key`, `_repository_cache`, `clear_repository_cache`, `_get_repository`, export, autouse conftest fixture
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: Optional code-scanning alerts in `get_pr_feedback` — [step_5.md](./steps/step_5.md)

- [ ] Implementation: tests + `include_alerts` parameter
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 6: `IssueBranchManager` accepts `github_token` — [step_6.md](./steps/step_6.md)

- [ ] Implementation: tests + `github_token` constructor pass-through
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 7: Public `repo_identifier` property — [step_7.md](./steps/step_7.md)

- [ ] Implementation: tests + property; switch `server.py`, `_permission_probes.py`, `base_branch_trust.py` to it
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
