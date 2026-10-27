# Step 1 — Query alerts by PR, `AlertData` shape, new alert line

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md` only.
> TDD: update/add the tests first, then the code. Use the MCP tools from CLAUDE.md.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy and vulture; all must pass.
> Run `run_format_code`, then make exactly one commit.
> If `fetch_code_scanning_alerts` no longer contains
> `parameters={"ref": f"refs/pull/{pr_number}/head"}`, write one line to
> `pr_info/.blocked.txt` and stop.

The 403 → `None` behaviour stays unchanged in this step (step 2 replaces it).

## WHERE

- `src/mcp_workspace/github_operations/pr_types.py`
- `src/mcp_workspace/github_operations/_pr_feedback_sources.py`
- `src/mcp_workspace/checks/pr_feedback.py`
- `tests/github_operations/test_pr_feedback_mixin.py`
- `tests/checks/test_branch_status_pr_feedback.py`

## Tests first

`tests/github_operations/test_pr_feedback_mixin.py`
- Add `"number": 51` and `"rule": {"id": "py/sql-injection", "description": "SQL injection"}`
  to the alert fixtures in the populated-state test and in
  `test_code_scanning_alerts_unpacks_two_tuple`.
- In both tests, assert the full dict:
  `{"number": 51, "rule_id": "py/sql-injection", "rule_description": "SQL injection",
  "message": "potential SQLi", "path": "src/foo.py", "line": 42}`.
- In `test_code_scanning_alerts_unpacks_two_tuple`, assert the exact request:
  ```python
  requester = mock_manager._github_client._Github__requester  # type: ignore[attr-defined]
  get_call = next(c for c in requester.requestJsonAndCheck.call_args_list if c.args[0] == "GET")
  assert get_call.args[1] == "/repos/test/repo/code-scanning/alerts"
  assert get_call.kwargs["parameters"] == {"pr": 42, "state": "open", "per_page": 100}
  ```

`tests/checks/test_branch_status_pr_feedback.py`
- `_alert()` returns `AlertData` (import it from `pr_types`):
  params `number: int = 51, rule_id: str = "py/sql-injection",
  rule_description: str = "SQL injection", message: str = "SQL injection vulnerability",
  path: str = "src/db.py", line: Optional[int] = 17`.
- Callers that pass `rule_description="py/sql-injection"` (`TestAlerts`,
  `TestMixedFullExample`) switch to `rule_id="py/sql-injection"`.
- `TestAlerts.test_alert_rendered`: assert the exact line
  `"[alert] [alert_number=51] py/sql-injection: SQL injection @ src/db.py:17"` is in
  `result.split("\n")`.
- `TestAlerts.test_alert_without_line_no`: build with `line=None`; assert the line
  `"[alert] [alert_number=51] py/sql-injection: SQL injection @ src/db.py"`.
- `TestCapOrdering` and the mixed example need no change beyond the helper.

## WHAT / HOW

`pr_types.py` — next to `ReviewThreadData`:
```python
class AlertData(TypedDict):
    """TypedDict for one open code-scanning alert on a PR."""

    number: int
    rule_id: str
    rule_description: str
    message: str
    path: str
    line: Optional[int]
```
`PRFeedback.alerts: list[AlertData]`. Drop `Any` from the `typing` import if unused.

`_pr_feedback_sources.py`
```python
def fetch_code_scanning_alerts(
    manager: "PullRequestManager", pr_number: int
) -> Optional[list["AlertData"]]:
```
- Add `AlertData` to the `TYPE_CHECKING` import from `.pr_types`.
- Docstring: "Fetch open code-scanning alerts for the PR via REST (first page only)."

`checks/pr_feedback.py` — alert loop renders the new line.

## ALGORITHM

```
data = GET code-scanning/alerts, parameters={"pr": pr_number, "state": "open", "per_page": 100}
for alert in data or []:
    instance, location, rule = most_recent_instance, its location, alert["rule"] (each `or {}`)
    append AlertData(number=alert["number"], rule_id=rule.id or "",
                     rule_description=rule.description or "", message=instance.message.text or "",
                     path=location.path or "", line=location.start_line)
```
Formatter:
```
location = f"{path}:{line_no}" if line_no else path
rendered.append(f"[alert] [alert_number={alert['number']}] {alert['rule_id']}: {alert['message']} @ {location}")
```

## DATA

- `fetch_code_scanning_alerts` → `Optional[list[AlertData]]` (`None` on 403 until step 2).
- `PRFeedback["alerts"]` → `list[AlertData]`.
