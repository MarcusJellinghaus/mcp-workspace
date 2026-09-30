# Step 3: GitHub integration tests for the query and for invalid-query responses

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md`: add two `github_integration` tests to `TestPullRequestManagerSmoke`. Run pylint, pytest (`-n auto`) and mypy; all must pass. If GitHub credentials are configured, also run `-m github_integration` on this file and report the result; if they aren't, say the tests were skipped. Make one commit.

## WHERE

- `tests/github_operations/test_github_integration_smoke.py`, class `TestPullRequestManagerSmoke`, after `test_basic_api_connectivity`

## WHAT

```python
def test_pr_feedback_query_accepted(self, pr_manager: PullRequestManager) -> None:
    """The reviewThreads query passes GitHub's schema validation."""

def test_invalid_graphql_query_returns_errors_without_data(
    self, pr_manager: PullRequestManager
) -> None:
    """GitHub answers an invalid query with HTTP 200, `errors`, and no `data` key."""
```

## HOW

- Reuse the existing `pr_manager` fixture. The class already has `@pytest.mark.github_integration`. No new fixtures or helpers.
- Test 2 gets the requester exactly as production does, with the same suppression comments:
  `pr_manager._github_client._Github__requester  # type: ignore[attr-defined]  # pylint: disable=protected-access`
- Test 2 calls `requestJsonAndCheck`, so a 4xx reply raises and fails the test. That's how the HTTP 200 assumption gets checked.

## ALGORITHM

Test 1 (real query):
```
prs = pr_manager.list_pull_requests(state="all", max_results=1)
if not prs: pytest.skip("test repo has no pull requests")
result = pr_manager.get_pr_feedback(prs[0]["number"])
assert "threads" not in result["unavailable"], result["unavailable"]
```

Test 2 (invalid query):
```
requester = pr_manager._github_client._Github__requester
_, body = requester.requestJsonAndCheck("POST", requester.graphql_url,
                                        input={"query": "query { viewer { notAField } }"})
assert "errors" in body
assert "data" not in body
```

## DATA

- `list_pull_requests` returns a list of dicts with a `"number"` key.
- `get_pr_feedback` returns a `PRFeedback` whose `"unavailable"` dict maps a source name to its exception.
- `requestJsonAndCheck` returns `(headers, body)`.

## Notes

- Use an existing PR, not one created during the test run: a brand-new PR can hit the not-found flake. Don't use a made-up PR number either: NOT_FOUND starts the retry loop. GitHub validates the query before it looks up the PR, so any existing PR will do.

## Done when

- pylint, pytest and mypy pass. Integration tests are skipped when credentials are missing, and pass when they're present.
- Commit message: `test(github_operations): add GraphQL integration smoke tests for PR feedback`
