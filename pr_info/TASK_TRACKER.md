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

### Step 1: Config switch `get_traffic_log_dir()` + autouse test fixture
See [step_1.md](./steps/step_1.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `traffic_log.py` writer module + architecture registration + concurrency probe
See [step_2.md](./steps/step_2.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy, lint-imports, tach — fix all issues
- [x] Commit message prepared

### Step 3: `__requestRaw` wrapper in `build_github_client`
See [step_3.md](./steps/step_3.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy, lint-imports, tach — fix all issues
- [ ] Commit message prepared

### Step 4: Retry lines in `_LoggingGithubRetry.increment` + end-to-end line counts
See [step_4.md](./steps/step_4.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: Raw download logging in `CIResultsManager`
See [step_5.md](./steps/step_5.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 6: `mcp-workspace server` command name in `main.py`
See [step_6.md](./steps/step_6.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy, lint-imports, tach — fix all issues
- [ ] Commit message prepared

### Step 7: README docs
See [step_7.md](./steps/step_7.md)

- [ ] Implementation (README `traffic_log` / `traffic_log_dir` docs, line format, hop semantics)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main`, address findings
- [ ] PR summary prepared
