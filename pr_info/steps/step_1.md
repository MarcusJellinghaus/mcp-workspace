# Step 1 — Combined linked-branch / closing-PR GraphQL query

## Prompt for LLM

Read `pr_info/steps/summary.md` for full context on issue #316, then implement this
step only. Follow TDD: write the tests first, confirm they fail for the right reason,
then implement until they pass. Run pylint, pytest (`-n auto`), and mypy per
CLAUDE.md; all must pass. Produce exactly one commit containing the tests and the
implementation together.

Precondition: `src/mcp_workspace/github_operations/issues/linked_branches_mixin.py`
must still contain `_LINKED_BRANCHES_QUERY`, `_query_linked_branches`,
`get_linked_branches`, `get_linked_branches_or_none`, and `delete_linked_branch`
exactly as today (none of them are touched by this step). If any is missing or
materially different, write one line to `pr_info/.blocked.txt` naming the mismatch
and stop.

## WHERE

- `src/mcp_workspace/github_operations/issues/linked_branches_mixin.py` — add new
  type, query constant, private parser, and public method.
- `src/mcp_workspace/github_operations/issues/__init__.py` — export the new type.
- `tests/github_operations/issues/test_branch_manager_linked.py` — new test class.

## WHAT

```python
class ClosingPRRef(NamedTuple):
    number: int
    head_ref_name: str
```

```python
def _query_linked_branch_and_closing_prs(
    manager: BaseGitHubManager, issue_number: int
) -> Optional[Tuple[List[str], List[ClosingPRRef]]]:
    ...
```

```python
class LinkedBranchesMixin:
    ...
    def get_linked_branch_and_closing_prs_or_none(
        self: "BaseGitHubManager", issue_number: int
    ) -> Optional[Tuple[List[str], List[ClosingPRRef]]]:
        ...
```

## HOW

- `_query_linked_branch_and_closing_prs` mirrors the existing
  `_query_linked_branches` exactly in shape and error handling (undecorated, returns
  `None` on any failure instead of raising) — reuse
  `validate_issue_number_or_log`, `manager._get_repository()`, and
  `manager._github_client._Github__requester.graphql_query(...)` the same way.
- Add a new module-level query constant,
  `_LINKED_BRANCH_AND_CLOSING_PRS_QUERY`, selecting both
  `linkedBranches(first: 100) { nodes { ref { name } } }` and
  `closedByPullRequestsReferences(first: 100, includeClosedPrs: false) { nodes { number headRefName } }`
  under the same `issue(number: $issueNumber)` selection — one request, two pieces of
  data.
- `get_linked_branch_and_closing_prs_or_none` mirrors
  `get_linked_branches_or_none` exactly: `@log_function_call` decorator, try/except
  around the private parser, logs and returns `None` on any `Exception`.
- Add `ClosingPRRef` to `__all__` in `linked_branches_mixin.py`, and to both the
  import block and `__all__` in `issues/__init__.py` (alongside `IssueBranchManager`).
- Do not modify `_LINKED_BRANCHES_QUERY`, `_query_linked_branches`,
  `get_linked_branches`, `get_linked_branches_or_none`, `delete_linked_branch`, or
  `_LINKED_BRANCHES_WITH_IDS_QUERY`.

## ALGORITHM

```
validate issue_number; get repo; build variables
run graphql_query(_LINKED_BRANCH_AND_CLOSING_PRS_QUERY, variables)
issue_data = result["data"]["repository"]["issue"]; None -> return None
branch_names  = [node.ref.name for node in issue_data.linkedBranches.nodes]
closing_prs   = [ClosingPRRef(node.number, node.headRefName)
                  for node in issue_data.closedByPullRequestsReferences.nodes]
return (branch_names, closing_prs)
```

## DATA

- Success: `Tuple[List[str], List[ClosingPRRef]]` — both lists possibly empty.
- Failure (invalid issue number, repo lookup failure, issue not found, malformed
  GraphQL response, or any exception): `None`.

## Tests to add (`tests/github_operations/issues/test_branch_manager_linked.py`)

New class `TestGetLinkedBranchAndClosingPRsOrNone`, following the existing
`mock_manager` fixture pattern in this file:

- `test_both_present` — mock GraphQL response with 1 linked branch and 1 closing PR
  node (`{"number": 42, "headRefName": "255-feature"}`); assert
  `(["255-feature"], [ClosingPRRef(42, "255-feature")])`.
- `test_no_closing_prs` — `closedByPullRequestsReferences.nodes = []`; assert the
  branch list is as given and closing-PR list is `[]`.
- `test_no_linked_branches` — `linkedBranches.nodes = []`; assert branch list `[]`
  and closing-PR list populated.
- `test_multiple_closing_prs` — two PR nodes; assert both come back as
  `ClosingPRRef` entries in order.
- `test_issue_not_found` — `{"data": {"repository": {"issue": None}}}`; assert
  `None`.
- `test_invalid_issue_number` — call with `0` and `-1`; assert `None` for each,
  without touching the mocked `graphql_query`.
- `test_malformed_response_returns_none` — response missing `headRefName` on a PR
  node; assert `None` (covers the `KeyError` branch).
