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

### Step 1: Missing-token degradation (port from fork), CI-only

See [step_1.md](./steps/step_1.md).

- [ ] Implementation: `CIStatus.UNAVAILABLE`, `GITHUB_TOKEN_HINT`, `get_github_token` import + token gate in `_collect_ci_status`, UNAVAILABLE rendering in `format_for_human` / `format_for_llm` / `_generate_recommendations`; tests in `tests/checks/test_branch_status.py` + patch existing `_collect_ci_status` tests in `tests/checks/test_branch_status_ci.py`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 2: Opt-in review-gate header (three-state, both formatters)

See [step_2.md](./steps/step_2.md).

- [ ] Implementation: `_review_gate_header` helper + `fail_on_reviews: bool = False` param on both `format_for_human` and `format_for_llm` with near-top insertion; tests in `tests/checks/test_branch_status.py`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues (confirm `branch_status.py` under 750-line limit)
- [ ] Commit message prepared

### Step 3: Configurable default + threading (`--fail-on-reviews`)

See [step_3.md](./steps/step_3.md).

- [ ] Implementation: thread `fail_on_reviews` through `async_poll_branch_status`, `_fail_on_reviews` global + `set_fail_on_reviews` + tool param + `run_server` in `server.py`, `--fail-on-reviews` argparse flag in `main.py`; tests in new `tests/test_server_fail_on_reviews.py`, `tests/checks/test_branch_status_polling.py`, `tests/test_reference_projects.py`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] Address PR review feedback
- [ ] Write PR summary
