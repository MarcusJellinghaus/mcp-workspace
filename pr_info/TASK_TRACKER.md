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

### Step 1: Remove `diffSide` from the reviewThreads query — [step_1.md](./steps/step_1.md)

- [ ] Implementation: remove `diffSide` from the query in `fetch_review_data` and the 7 test fake entries
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 2: Don't retry a GraphQL response that has errors and no `data` — [step_2.md](./steps/step_2.md)

- [ ] Implementation: tests first (parametrized `_has_permanent_error` test, `test_null_data_with_untyped_error_retried`, rewrite `test_null_pull_request_with_error_flagged`), then the no-`data` rule and comment/docstring updates
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 3: GitHub integration tests for the query and invalid-query responses — [step_3.md](./steps/step_3.md)

- [ ] Implementation: add `test_pr_feedback_query_accepted` and `test_invalid_graphql_query_returns_errors_without_data` to `TestPullRequestManagerSmoke`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main`
- [ ] PR summary prepared
