# Step 2: Don't retry a GraphQL response that has errors and no `data`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md`. Write the tests first and watch them fail, then change `_has_permanent_error` and update the comments and docstrings. Run pylint, pytest (`-n auto`) and mypy; all must pass. Make one commit.

## WHERE

- `src/mcp_workspace/github_operations/_pr_feedback_sources.py`
- `tests/github_operations/test_pr_manager_feedback.py`

## WHAT

### Tests (write first)

1. **New module-level parametrized test** (no fixture needed). Add `_has_permanent_error` to the existing `_pr_feedback_sources` import.
   ```python
   @pytest.mark.parametrize(
       ("result", "expected"),
       [
           ({"errors": [{"message": "Field 'x' doesn't exist"}]}, True),  # no data key
           ({"data": None, "errors": [{"message": "timeout"}]}, False),  # data: null
       ],
   )
   def test_has_permanent_error_keys_on_data_presence(
       result: dict[str, Any], expected: bool
   ) -> None:
       assert _has_permanent_error(result) is expected
   ```
2. **New loop-level test in `TestGetPRFeedback`**, next to `test_null_pull_request_no_errors_flagged`:
   `test_null_data_with_untyped_error_retried`
   - `graphql_response={"data": None, "errors": [{"message": "Something went wrong while executing your query."}]}`
   - Patch `_pr_feedback_sources.time.sleep`.
   - Assert `_post_call_count(mock_manager) == 3`, `sleep.call_count == 2`, and `"threads" in result["unavailable"]`.
3. **Rewrite `test_null_pull_request_with_error_flagged`:**
   - Build the body inline, with no `data` key: `graphql_response={"errors": [{"message": "Field 'x' doesn't exist on type 'Y'"}]}`. Don't use `_null_pr_body`, because it always adds `data`.
   - Expect `_post_call_count(mock_manager) == 1` and `sleep.assert_not_called()`.
   - Keep the existing rendered-message assertion unchanged.
   - Update its docstring to say that an invalid query fails once, without retrying.

### Implementation

`_has_permanent_error(result: dict[str, Any]) -> bool` keeps its signature. Add one early return after the `isinstance` check:

## ALGORITHM

```
errors = result.get("errors")
if errors is not a list: return False
if "data" not in result: return True        # invalid query: errors and no data key
return any(entry["type"] in _PERMANENT_GRAPHQL_ERROR_TYPES for dict entries)
```

## HOW

- The retry loop in `fetch_review_data` stays unchanged; it already breaks when `_has_permanent_error` returns True.
- `_build_graphql_exception` stays unchanged too. It still builds the 400 exception from `errors`, so the rendered message is the same.
- Update the wording in three places:
  - **Module comment** (the reviewThreads retry-config block near the top): retries stop when a typed error is permanent **or** the response has `errors` and no `data` key, meaning GraphQL rejected the query at validation. `"data": null` (a timeout) is still retried.
  - **`_has_permanent_error` docstring:** describe both rules. Explain why a missing `data` key is the marker and a missing `type` isn't: the not-found flake has no `type` either, but it does return `data`.
  - **`fetch_review_data` docstring:** change "no error type is permanent" to "no error is permanent", and note that a response with errors and no `data` isn't retried.

## DATA

`_has_permanent_error` still returns `bool`.

| Response | Result |
|---|---|
| `errors` list, no `data` key | True |
| `"data": None` with an untyped error | False |
| `data` with null `pullRequest` and an untyped error | False |
| An error typed `FORBIDDEN` / `INSUFFICIENT_SCOPES` / `RATE_LIMITED` | True (unchanged) |

## Done when

- The new and rewritten tests fail before the implementation change and pass after it.
- `test_review_data_retry_then_success` and the other existing retry tests still pass.
- pylint, pytest and mypy pass.
- Commit message: `fix(github_operations): stop retrying GraphQL responses without data`
