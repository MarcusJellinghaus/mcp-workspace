# Step 5 — Optional code-scanning alerts in `get_pr_feedback`

## LLM prompt
Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_5.md`)
only. Write the tests first, then the implementation. Run pylint, pytest
(`-n auto`) and mypy; all must pass. Run format_code, then make exactly one commit.

## WHERE
- `src/mcp_workspace/github_operations/pr_feedback_mixin.py` — `get_pr_feedback`
- `tests/github_operations/test_pr_feedback_mixin.py`

## WHAT
```python
def get_pr_feedback(
    self: "PullRequestManager", pr_number: int, include_alerts: bool = True
) -> PRFeedback
```

## HOW
- Decorators unchanged (`@log_function_call`, `@_handle_github_errors`).
- Docstring: document `include_alerts` (when False, no code-scanning request;
  `alerts` is `[]` and neither `unavailable` nor `skipped` has an `"alerts"` key).
- `checks/pr_feedback.py` keeps calling with the default — no change there.

## ALGORITHM
```
alerts = []
if include_alerts:
    try: alerts = fetch_code_scanning_alerts(self, pr_number)
    except ...: existing skipped/unavailable handling (unchanged)
```

## DATA
`PRFeedback` shape unchanged.

## Tests (`test_pr_feedback_mixin.py`)
- `include_alerts=False` → `fetch_code_scanning_alerts` not called;
  `alerts == []`; `"alerts"` not in `unavailable` or `skipped`; threads and
  comments still fetched.
- Default call → `fetch_code_scanning_alerts` called once (existing tests cover
  the 403/other-error paths).
