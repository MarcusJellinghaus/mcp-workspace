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

### Step 1: Pytest timeout config — `pytest-timeout = 2400` ([step_1.md](./steps/step_1.md))
- [x] Implementation: add `pytest-timeout = 2400` to `[tool.mcp-tools-py]` in `pyproject.toml`; confirm config loads with one small test file
- [x] Quality checks (pylint, mypy, format) — fix all issues
- [x] Commit message prepared

### Step 2: Issue manager fixtures in repo_url mode + markers ([step_2.md](./steps/step_2.md))
- [ ] Implementation: add `make_issue_manager()`, remove `real_issue_manager`, simplify `mock_issue_manager`, update the two former callers, fix `git_integration` markers; run the listed test files
- [ ] Quality checks (ruff, vulture, pylint, mypy, format) — fix all issues
- [ ] Commit message prepared

### Step 3: PR manager fixtures in repo_url mode + markers ([step_3.md](./steps/step_3.md))
- [ ] Implementation: rewrite the six PullRequestManager fixtures to repo_url mode, drop token patches and unused imports, remove `git_integration` from the six classes; run the six test files
- [ ] Quality checks (ruff, vulture, pylint, mypy, format) — fix all issues
- [ ] Commit message prepared

### Step 4: One push for 120 branches ([step_4.md](./steps/step_4.md))
- [ ] Implementation: replace 119 `update_ref` + `push --all` in `test_many_branches_not_truncated` with a single push of 120 refspecs; run `test_remote_queries.py`
- [ ] Quality checks (pylint, mypy, format) — fix all issues
- [ ] Commit message prepared

### Step 5: Fewer `Repo` objects in test helpers ([step_5.md](./steps/step_5.md))
- [ ] Implementation: convert `repo.git.<cmd>`-only helpers to `git.Git`, one `Repo` per test for object-model helpers, replace throwaway `Repo.init(...).close()`, apply decision 4; run changed test files; `.scratch/` removed
- [ ] Quality checks (ruff, vulture, pylint, mypy, format) — fix all issues
- [ ] Commit message prepared

### Step 6: Marker audit of remaining modules ([step_6.md](./steps/step_6.md))
- [ ] Implementation: add/narrow/remove `git_integration` markers per decision 1, no double group markers (decision 2); verify with `--collect-only` and run changed files
- [ ] Quality checks (pylint, mypy, format) — fix all issues
- [ ] Commit message prepared

## Pull Request
- [ ] PR review: review full branch diff against `main`, address findings
- [ ] PR summary prepared
