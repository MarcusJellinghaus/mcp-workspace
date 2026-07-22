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

### Step 1: Inline bounded retry for the reviewThreads GraphQL query (TDD)

Detail: [step_1.md](./steps/step_1.md)

- [ ] Implementation: add the three tests (TDD) — `test_review_data_retry_then_success`, `test_review_data_retry_exhausted_unavailable`, and the extension of `test_graphql_failure` — then add `import time`, the `_REVIEW_DATA_*` constants, and the bounded retry loop around the `graphql_query` call in `fetch_review_data`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] Review the PR (address feedback)
- [ ] Write the PR summary
