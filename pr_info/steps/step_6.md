# Step 6 — `detect_base_branch` reads only `issue_data` (no double fetch)

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_6.md`). Implement
> step 6 only: tests first, then remove the `issue_manager` parameter and the issue-fetch path
> from `detect_base_branch` / `_detect_from_issue`, and drop the argument at its last caller
> (`collect_branch_status`). Run pylint, pytest (`-n auto`) and mypy until green, run
> `run_format_code`, then make one commit.

## Precondition

Search `src/` for `issue_manager=` passed to `detect_base_branch`. The only caller expected to
pass it is `checks/branch_status.py::collect_branch_status` (`get_base_branch` stopped in
step 5). If any other caller passes it, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/git_operations/base_branch.py`
- `src/mcp_workspace/checks/branch_status.py` — drop `issue_manager=issue_manager`
- `tests/git_operations/test_base_branch.py`

## WHAT

```python
def _detect_from_issue(issue_data: Optional["IssueData"]) -> Optional[str]: ...

def detect_base_branch(
    project_dir: Path,
    current_branch: Optional[str] = None,
    issue_data: Optional["IssueData"] = None,
    pr_manager: Optional["PullRequestManager"] = None,
) -> Optional[str]: ...
```

## HOW

- `TYPE_CHECKING` import becomes `from mcp_workspace.github_operations.issues import IssueData`.
- Remove the now-unused `extract_issue_number_from_branch` import.
- Docstrings: module docstring and `detect_base_branch` say the issue's base branch comes from
  the caller-supplied `issue_data`; callers must check `base_branch_error` before calling
  (a malformed section is not this module's concern).
- `collect_branch_status`: keep `issue_manager` (still used for `get_comments`), just stop
  passing it to `detect_base_branch`.

## ALGORITHM

```
if issue_data is not None and issue_data.get("base_branch"):
    logger.debug("Detected base branch from provided issue_data: '%s'", ...)
    return issue_data["base_branch"]
return None
```

## DATA

Unchanged: `Optional[str]`.

## Tests (write first)

- `TestDetectFromIssue`: update to the one-argument signature; keep
  `test_returns_base_branch_from_issue_data`, `test_returns_none_when_issue_data_has_no_base_branch`,
  and a `None` case; delete the four manager-fetch tests
  (`test_fetches_issue_via_manager_when_no_issue_data`, `..._no_issue_number`,
  `..._fetched_issue_is_empty`, `..._manager_raises_exception`).
- `TestDetectBaseBranch` stays green (no test passes `issue_manager`).
- Existing `tests/checks/test_branch_status*.py` stay green.
