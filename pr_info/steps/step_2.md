# Step 2 — Create `test_types.py` (`create_empty_issue_data`)

> Read `pr_info/steps/summary.md` first. This is Step 2 of 6. One commit.

## Kind
TDD, new coverage. `create_empty_issue_data` is currently only *used* (once, as a mock
`return_value`), never *tested*. Source already exists — add the first dedicated tests.
Minimal file: cover the factory only; **skip** thin `TypedDict`/`Enum` tests.

## WHERE
- New file: `tests/github_operations/issues/test_types.py`

## WHAT — function under test
```python
# src/mcp_workspace/github_operations/issues/types.py
def create_empty_issue_data() -> IssueData: ...
```
Returns an `IssueData` with: `number=0`, `title=""`, `body=""`, `state=""`, `labels=[]`,
`assignees=[]`, `user=None`, `created_at=None`, `updated_at=None`, `url=""`,
`locked=False`. `base_branch` is `NotRequired` and is **not** set.

## HOW — imports
```python
from mcp_workspace.github_operations.issues.types import create_empty_issue_data
```
No mocking, no fixtures, no marker (pure function → plain unit test).

## ALGORITHM (test logic)
```
test_returns_all_default_fields:      call once, assert every field equals the default above
test_base_branch_key_absent:          assert "base_branch" not in the returned dict
test_returns_independent_instances:   call twice; mutate first result's labels/assignees;
                                       assert second call's lists are still empty (fresh dict per call)
```

## DATA
Return value is the `IssueData` TypedDict (a plain `dict` at runtime). Assertions are exact
equality per field plus list-independence.

## Verify (MCP tools only)
- `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","tests/github_operations/issues/test_types.py"])`
  — new tests pass against existing source.
- `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_mypy_check`.

## Done when
`test_types.py` exists, ~3 focused tests pass, checks green. One commit.

## LLM prompt
> Implement Step 2 from `pr_info/steps/step_2.md` (context in `pr_info/steps/summary.md`).
> Create `tests/github_operations/issues/test_types.py` with focused unit tests for
> `create_empty_issue_data` only (all default fields; `base_branch` key absent; each call
> returns independent list objects). No mocking, no fixtures. Verify with
> `mcp__tools-py__run_pytest_check`, then pylint and mypy. Follow all `CLAUDE.md` rules
> (MCP tools only; `./tools/format_all.sh` before committing). Produce exactly one commit.
