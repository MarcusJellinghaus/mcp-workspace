# Summary: Fix invalid `diffSide` field in the reviewThreads query (#304)

## Problem

`fetch_review_data` selects `diffSide` on `PullRequestReviewComment`, which has no such field. That field only exists on `PullRequestReviewThread`. GraphQL validates the whole query before running it, so every call fails, and all PR review feedback (threads and reviews) is reported as unavailable. The unit tests mock the response, so the query text never reached GitHub.

On top of that, the retry loop treats the validation error as transient. It makes 3 attempts and sleeps 1s + 2s on a request that can never succeed.

## Design changes

1. **Query fix.** Remove `diffSide` from the comment selection. Nothing reads it, so it isn't moved to the thread level.
2. **Permanent-error rule.** `_has_permanent_error` gains one rule: if the response has an `errors` list and **no `data` key**, the failure is permanent. The existing typed rule (`FORBIDDEN`, `INSUFFICIENT_SCOPES`, `RATE_LIMITED`) is unchanged.
   - An invalid query returns `errors` with no `data` key, as the GraphQL spec requires. It is no longer retried.
   - `"data": null` (GitHub query timeout) is still retried.
   - `data` with a null `pullRequest` (the not-found flake for a brand-new PR) is still retried.
   - "An error without a `type`" is deliberately *not* the rule, because the not-found flake also has no `type`.
3. **Integration coverage.** Two `github_integration` smoke tests send real queries to GitHub:
   - The production query runs against an existing PR and is accepted.
   - An invalid query comes back as HTTP 200 with `errors` and no `data` key. This confirms the assumption behind change 2.

No new modules, dependencies, constants or helpers. There is no offline schema validation (the issue decided against it).

## Files modified

| File | Change |
|---|---|
| `src/mcp_workspace/github_operations/_pr_feedback_sources.py` | Remove `diffSide` from the query; add the no-`data` rule to `_has_permanent_error`; update the module comment and the `_has_permanent_error` and `fetch_review_data` docstrings |
| `tests/github_operations/test_pr_manager_feedback.py` | Remove the 7 `"diffSide": "RIGHT"` entries; add a parametrized `_has_permanent_error` test and a `data: null` loop test; rewrite `test_null_pull_request_with_error_flagged` |
| `tests/github_operations/test_github_integration_smoke.py` | Add 2 tests to `TestPullRequestManagerSmoke` |

No files or folders are created apart from these planning documents.

## Steps

1. [step_1.md](./step_1.md): Remove `diffSide` from the query and the test fakes.
2. [step_2.md](./step_2.md): Treat "errors and no `data` key" as permanent.
3. [step_3.md](./step_3.md): Add the GitHub integration tests.
