# Step 1 — Extract the GraphQL retry loop into a reusable helper

See `pr_info/steps/summary.md` for full architecture and context. This step is a pure refactor: no observable behavior change, no query text change, no field renames. It exists so step 2 and step 4 can both reuse the same retry/permanent-error policy instead of duplicating it.

## WHERE

- `src/mcp_workspace/github_operations/_pr_feedback_sources.py` — new function, `fetch_review_data` updated to call it.
- `tests/github_operations/test_pr_feedback_mixin.py` — new direct unit tests for the helper; all existing tests in this file must keep passing unmodified (if any existing assertion needs to change, the refactor broke behavior — stop and fix the refactor, not the test).

## WHAT

```python
def _request_review_page(
    requester: Requester, query: str, variables: dict[str, Any]
) -> Tuple[dict[str, Any], Optional[dict[str, Any]], Optional[GithubException]]:
    """Run one GraphQL request under the existing retry/permanent-error policy.

    Returns:
        (headers, pr_data, error) — pr_data is the repository.pullRequest
        payload, or None; error is what graphql_query would have raised, or
        None. Recovered pr_data is returned alongside error, never instead of it.
    """
```

## HOW

- `_has_permanent_error` and `_build_graphql_exception` are unchanged and called from inside `_request_review_page` exactly as they are today from `fetch_review_data`.
- `fetch_review_data` replaces its inline `for attempt in range(_REVIEW_DATA_MAX_ATTEMPTS):` block with a single call: `headers, pr_data, error = _request_review_page(requester, query, variables)`.
- `fetch_review_data` keeps its own `if pr_data is None: return ([], 0, [], error)` guard and the rest of its parsing unchanged in this step.
- Module-level constants `_REVIEW_DATA_MAX_ATTEMPTS`, `_REVIEW_DATA_RETRY_BASE_DELAY_SECONDS`, `_PERMANENT_GRAPHQL_ERROR_TYPES` stay where they are, read by the new helper.

## ALGORITHM

```
for attempt in range(MAX_ATTEMPTS):
    headers, result = requester.requestJsonAndCheck(POST, graphql_url, {query, variables})
    pr_data = dig(result, "data", "repository", "pullRequest")  # or-{} at every level
    if pr_data is not None or _has_permanent_error(result):
        break
    if attempt is last:
        break
    sleep(BASE_DELAY * 2 ** attempt)
error = _build_graphql_exception(requester, headers, result)
if error is None and pr_data is None:
    error = GithubException(200, {"errors": [{"message": "pullRequest not returned"}]}, headers)
return headers, pr_data, error
```

## DATA

Same tuple shape `fetch_review_data` already builds internally today — this step only moves it into a named, independently testable function. No change to `fetch_review_data`'s own return type.

## Tests (write first)

Add direct tests calling `_request_review_page` (not going through `get_pr_feedback`), reusing the existing mock-requester setup pattern from this test file:

- success on the first attempt → no sleep, `pr_data` populated, `error is None`.
- null `pullRequest` + non-permanent error, then success → one retry, `sleep` called once.
- null `pullRequest` + non-permanent error persisting → 3 attempts, `sleep` called twice, synthesized status-200 error.
- a permanent error type (`FORBIDDEN`) → 1 attempt, no sleep.
- a lone `NOT_FOUND` error → `UnknownObjectException`, status 404.
- two errors in one response → plain `GithubException`, status 400.

Then run the full existing `TestGetPRFeedback` class unmodified to confirm the refactor preserves behavior exactly.

## Commit

One commit: new tests + `_request_review_page` + `fetch_review_data` updated to call it. `ruff`/`pylint`/`pytest -n auto`/`mypy` all green.

## LLM Prompt

> Implement `pr_info/steps/step_1.md` for issue #324 (architecture and rationale in `pr_info/steps/summary.md`). This is a pure refactor — no query text, field name, or return-type changes. Follow TDD: add the direct `_request_review_page` tests first, confirm they fail against the current inline-loop code (there is nothing to call yet), then extract the helper and get them green, then confirm every existing test in `tests/github_operations/test_pr_feedback_mixin.py` still passes unmodified. Run `mcp__mcp-tools-py__run_ruff_check`, `run_pylint_check`, `run_pytest_check` (with `extra_args: ["-n", "auto"]`), and `run_mypy_check` until clean, then make exactly one commit.
