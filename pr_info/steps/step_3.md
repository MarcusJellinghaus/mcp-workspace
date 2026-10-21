# Step 3 — `IssueData.base_branch_error` + log-once

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_3.md`). Implement
> step 3 only: tests first, then add `base_branch_error` to `IssueData` and populate it via
> one helper in `manager.py` that also logs the WARNING once per (repo, issue, message).
> Run pylint, pytest (`-n auto`) and mypy until green, run `run_format_code`, then make one
> commit.

## WHERE

- `src/mcp_workspace/github_operations/issues/types.py`
- `src/mcp_workspace/github_operations/issues/manager.py`
- `tests/github_operations/issues/test_manager_base_branch.py` (new)
- `tests/github_operations/conftest.py` — autouse reset fixture

## WHAT

```python
# types.py — IssueData
base_branch_error: NotRequired[Optional[str]]

# manager.py
_warned_malformed_base_branch: set[tuple[str, int, str]] = set()

def _parse_base_branch_fields(
    body: str, repo_full_name: str, issue_number: int
) -> tuple[Optional[str], Optional[str]]:
    """Return (base_branch, base_branch_error) for an issue body."""
```

## HOW

- Import `MalformedBaseBranchError`, `format_malformed_base_branch` from `.base`.
- `get_issue`: `base_branch, base_branch_error = _parse_base_branch_fields(body, repo.full_name, issue_number)`;
  pass both into `IssueData(...)`.
- `_list_issues_no_error_handling`: same, with `issue.number`.
- Catch only `MalformedBaseBranchError` (not `ValueError`).
- `labels_mixin.py` / `_issue_to_data` are untouched (NotRequired).
- `cache.py` needs no change (old JSON entries simply lack the key).

## ALGORITHM

```
try: return parse_base_branch(body), None
except MalformedBaseBranchError as exc:
    message = format_malformed_base_branch(exc)
    key = (repo_full_name.lower(), issue_number, message)
    level = logging.DEBUG if key in _warned_malformed_base_branch else logging.WARNING
    _warned_malformed_base_branch.add(key)
    logger.log(level, "Issue #%d has malformed base branch: %s", issue_number, message)
    return None, message
```

## DATA

- Valid section → `("feature/x", None)`; absent / empty → `(None, None)`;
  multi-line → `(None, "<helper sentence>")`.

## Tests (new file, write first)

Use the `mock_issue_manager` fixture and `make_mock_issue` (see `test_manager.py`); the
fixture's repo has `full_name = "test/repo"`.

- `get_issue` with `"### Base Branch\n\nepic/x\nmore"` → `base_branch is None`,
  `base_branch_error` == helper sentence (`First line: 'epic/x'`).
- `get_issue` valid / absent / empty section → `base_branch_error is None`.
- `list_issues` same two cases.
- Log once: two `get_issue` calls on the same malformed issue → exactly one WARNING record,
  second record is DEBUG (`caplog.set_level(logging.DEBUG)`).
- Different issue number → its own WARNING.

Fixture in `tests/github_operations/conftest.py`:

```python
@pytest.fixture(autouse=True)
def _reset_malformed_base_branch_warnings() -> Iterator[None]:
    manager_module._warned_malformed_base_branch.clear(); yield
    manager_module._warned_malformed_base_branch.clear()
```
