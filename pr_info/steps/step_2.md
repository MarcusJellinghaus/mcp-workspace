# Step 2 — `IssueData.author_association` and one shared `issue_to_data`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md`.
> TDD: write the tests listed below first, see them fail, then implement.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy until all pass, then
> `run_format_code` and make one commit.

## WHERE

- `src/mcp_workspace/github_operations/issues/types.py`
- `src/mcp_workspace/github_operations/issues/manager.py`
- `src/mcp_workspace/github_operations/issues/labels_mixin.py`
- `tests/github_operations/_issue_test_helpers.py`
- Every test `IssueData(...)` construction site that mypy reports
- `issue_to_data` / `create_empty_issue_data` tests in
  `tests/github_operations/issues/test_types.py` (existing module; mirrors src)
- `get_issue` / `list_issues` / labels-mixin `author_association` tests in the existing
  manager test modules (e.g. `tests/github_operations/issues/test_manager_base_branch.py`)

## WHAT

```python
# types.py
class IssueData(TypedDict):
    ...
    author_association: Optional[str]   # required, after `locked`

def issue_to_data(github_issue: "Issue") -> IssueData:
    """Convert a PyGithub Issue into IssueData (without base_branch fields)."""
```

- `create_empty_issue_data()` sets `author_association=None`.
- Add `issue_to_data` to `__all__`.

## HOW

- Move the body of `_issue_to_data` from `manager.py` into `types.py` as
  `issue_to_data`. Add
  `author_association=normalize_author_association(github_issue.author_association)`
  (`from ..trust import normalize_author_association`; `trust.py` imports only `typing`).
- Import `Issue` under `if TYPE_CHECKING:` so `types.py` stays cheap to import.
- `manager.py`: delete `_issue_to_data` and import `issue_to_data`. `create_issue`,
  `close_issue`, `reopen_issue` and `edit_issue` call it.
- `get_issue` and `_list_issues_no_error_handling` replace their hand-built `IssueData(...)`:
  ```python
  data = issue_to_data(github_issue)
  data["base_branch"], data["base_branch_error"] = _parse_base_branch_fields(
      data["body"], repo.full_name, github_issue.number
  )
  ```
  The parse call is unchanged; step 4 gates it.
- `labels_mixin.py`: `add_labels`, `remove_labels` and `set_labels` return
  `issue_to_data(github_issue)` instead of a hand-built `IssueData`.
- `make_mock_issue` sets `mock_issue.author_association = "OWNER"`, and test `IssueData`
  fixtures pass `author_association="OWNER"`. A bare `MagicMock` attribute would
  normalise to `None` (untrusted) and break the base-branch and cache tests once step 4
  lands.

## DATA

- `IssueData` gains `author_association: Optional[str]`: a string from GitHub, `None`
  for non-string values and empty data.

## Tests (write first)

- `issue_to_data` copies `author_association="MEMBER"` from a mock issue, and maps a
  non-`str` value (`MagicMock()`, `None`, `5`) to `None`.
- `issue_to_data` with `user=None` → `user is None`.
- `get_issue` and `list_issues` results carry `author_association`.
- `add_labels`, `remove_labels` and `set_labels` results carry `author_association`.
- `create_empty_issue_data()["author_association"] is None`.
- The existing suite passes, and mypy is clean over `src/` and `tests/`.
