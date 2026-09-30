# Step 1: Remove `diffSide` from the reviewThreads query

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md`: remove the invalid `diffSide` field from the GraphQL query and from the test fakes. Run pylint, pytest (`-n auto`) and mypy; all must pass. Make one commit.

## WHERE

- `src/mcp_workspace/github_operations/_pr_feedback_sources.py`: the query in `fetch_review_data`
- `tests/github_operations/test_pr_manager_feedback.py`: the fake GraphQL responses

## WHAT

- Query comment selection becomes:
  ```graphql
  nodes { author { login } body path line diffHunk }
  ```
- Delete every `"diffSide": "RIGHT",` line from the test file (7 entries). Nothing else in those dicts changes.

No function signatures change.

## HOW

- This is a plain text edit. The parser in `fetch_review_data` never reads `diffSide`, so no parsing code changes.
- TDD doesn't apply here: the bug is in query text that mocks never send to GitHub. Step 3 adds the test that covers it.

## ALGORITHM

None.

## DATA

Unchanged. Unresolved threads are still `{"path", "line", "author", "body", "diff_hunk"}`.

## Done when

- `search_files(pattern="diffSide")` returns no matches under `src/` or `tests/`.
- pylint, pytest and mypy pass.
- Commit message: `fix(github_operations): drop invalid diffSide from reviewThreads query`
