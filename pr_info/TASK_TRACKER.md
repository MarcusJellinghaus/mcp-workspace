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

### Step 1: GitHub client factory (Part A) + PyGithub floor bump
See [step_1.md](./steps/step_1.md)

- [x] Implementation: create `_client.py` factory + `test_client.py`, repoint the three bare `Github()` call sites (base_manager x2, verification), bump `PyGithub>=2.1.0` in `pyproject.toml`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared (confirmed: .gitignore:48 lists pr_info/.commit_message.txt and MCP save_file blocks gitignored paths; no Bash/Write tool in this session, so the exact file cannot be written from here — message text recorded in the run output / PR notes)

### Step 2: Bounded connect timeout on raw artifact download (Part A′)
See [step_2.md](./steps/step_2.md)

- [ ] Implementation: add `DEFAULT_CONNECT_TIMEOUT` constant + `(connect, read)` timeout tuple in `ci_results_manager.py`, add timeout-assertion test
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 3: Network diagnostics helper + once-per-process error logging (Part B)
See [step_3.md](./steps/step_3.md)

- [ ] Implementation: create `_network.py` (diagnostics + once-per-process log) + `test_network.py`, wire `maybe_log_network_diagnostics` at 3 sites, add conftest guard-reset fixture
- [ ] Quality checks: pylint, pytest, mypy, lint_imports — fix all issues
- [ ] Commit message prepared

### Step 4: Verify `network_proxy` probe + verify-local short-circuit (Parts C + C′)
See [step_4.md](./steps/step_4.md)

- [ ] Implementation: add `has_applicable_proxy` to `_network.py`, add `network_proxy` CheckResult + short-circuit in `verification.py`, extend `test_verification.py`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] Address PR review feedback
- [ ] Final summary of changes
