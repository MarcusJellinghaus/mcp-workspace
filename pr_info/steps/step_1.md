# Step 1 — Non-swallowing linked-branch lookup on `IssueBranchManager`

**Goal:** add a way to distinguish "the issue genuinely has no linked branch"
from "the lookup failed", without changing anything about the existing
`get_linked_branches`.

See [summary.md](./summary.md), section *1. A non-swallowing lookup path*.

## WHERE

| File | Change |
|---|---|
| `src/mcp_workspace/github_operations/issues/branch_manager.py` | Split `get_linked_branches` into a private query + two thin wrappers |
| `tests/github_operations/issues/test_branch_manager_linked.py` | Add cases for the new method to the existing `TestGetLinkedBranches` class (or a sibling class in the same file) |

## WHAT

Replace the single decorated `get_linked_branches` (currently at
`branch_manager.py:164-241`) with three methods:

```python
def _query_linked_branches(self, issue_number: int) -> Optional[List[str]]:
    """Query linked branches via GraphQL, undecorated.

    Returns:
        List of branch names on success (possibly empty), or None when the
        lookup could not be completed.
    """

@log_function_call
@_handle_github_errors(default_return=[])
def get_linked_branches(self, issue_number: int) -> List[str]:
    """Unchanged public behaviour: [] on any failure."""

def get_linked_branches_or_none(self, issue_number: int) -> Optional[List[str]]:
    """Same query, but None on any failure instead of []."""
```

`Optional` and `List` are already imported (`branch_manager.py:7`). No new
imports.

## HOW

- `_query_linked_branches` is the **existing body verbatim**, with its four
  `return []` statements changed to `return None`, and its logging left exactly
  as it is (`logger.error("Failed to get repository")`, `logger.warning(f"Issue
  #{issue_number} not found")`, `logger.error(f"Error parsing GraphQL response:
  {e}")`). It carries **no decorators**.
- `get_linked_branches` keeps both decorators and its full docstring, and
  becomes a two-line body. Because the private method returns `None` rather
  than raising, the decorator sees no new exception and the invalid-issue-number
  path still returns `[]` with no extra log line — behaviour and logging are
  identical to today.
- **Do not** signal failure with an exception. `_handle_github_errors` re-raises
  `ValueError` (`base_manager.py:75-77`), and any other exception type would
  add a spurious `Unexpected error in ...` log to the invalid-number path. The
  `None` sentinel avoids both.
- `get_linked_branches_or_none` is undecorated and catches `Exception` broadly
  (`# pylint: disable=broad-exception-caught`), returning `None`. It does
  **not** re-raise 401/403: for the caller in step 2 an auth failure is exactly
  an undeterminable lookup.

## ALGORITHM

```
_query_linked_branches(issue_number):
    if not _validate_issue_number(...):        return None   # was []
    repo = _get_repository();  if repo is None: return None   # was []
    _, result = graphql_query(...)                            # may raise
    issue = result["data"]["repository"]["issue"]
    if issue is None:                           return None   # was []
    try:    return [n["ref"]["name"] for n in nodes if n and n.get("ref")]
    except (KeyError, TypeError):               return None   # was []

get_linked_branches(n):          r = _query(n); return [] if r is None else r
get_linked_branches_or_none(n):  try: return _query(n)  except Exception: return None
```

## DATA

- `_query_linked_branches` → `Optional[List[str]]`. Short branch names
  (GraphQL `Ref.name`, no `refs/heads/` prefix). `[]` means "queried fine, no
  linked branches"; `None` means "could not determine".
- `get_linked_branches` → `List[str]`, unchanged contract.
- `get_linked_branches_or_none` → `Optional[List[str]]`.

## TDD — tests first

The file already has a `mock_manager` fixture (`test_branch_manager_linked.py:17`)
that patches the git-repo check, the token and the `Github` client; reuse it and
the existing mocking style (`mock_manager._repository = mock_repo`, then
`mock_manager._github_client._Github__requester.graphql_query = Mock(...)`).

New tests for `get_linked_branches_or_none`:

1. success with two branches → `["123-feature-branch", "123-hotfix"]`
2. successful query, empty `nodes` → `[]` (**not** `None` — this is the
   `NOT_LINKED` case and the distinction is the whole point of the step)
3. invalid issue number (`0` and `-1`) → `None`
4. `_get_repository()` returns `None` → `None`
5. GraphQL `issue` is null → `None`
6. malformed payload (`{"data": None}`) → `None`
7. `graphql_query` raises `GithubException(500, ...)` → `None`
8. `graphql_query` raises `GithubException(401, ...)` → `None` (documents that
   the sibling does not re-raise auth errors)

**Do not modify the five existing `assert result == []` tests** (six assertions,
at `test_branch_manager_linked.py:73,77,96,117,170,180`). They cover all four
failure paths of `get_linked_branches` and are the regression harness proving
the refactor changed nothing for existing callers.

## Definition of done

- New tests fail before the refactor, pass after.
- All existing `test_branch_manager_linked.py` and
  `test_branch_manager_create.py` tests still pass unmodified.
- `mcp__tools-py__run_pylint_check`, `run_mypy_check` and `run_pytest_check`
  (with `-n auto` and the integration-marker exclusions) all pass.
- One commit.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`.
>
> Implement step 1 only: split `IssueBranchManager.get_linked_branches` into an
> undecorated `_query_linked_branches` returning `Optional[List[str]]` (the four
> in-body failure paths return `None` instead of `[]`), a decorated
> `get_linked_branches` wrapper preserving today's `[]` contract exactly, and a
> new `get_linked_branches_or_none` returning `None` on any failure.
>
> Write the tests first, in the existing
> `tests/github_operations/issues/test_branch_manager_linked.py`, reusing its
> `mock_manager` fixture. Cover all eight cases listed in step_1.md — in
> particular that a successful query with no linked branches returns `[]`, not
> `None`. Do not modify the existing `assert result == []` tests; they must keep
> passing untouched.
>
> Do not use an exception to signal failure from the private method — see the
> HOW section for why. Do not change `get_linked_branches`' `default_return`.
> Do not touch `checks/branch_status.py` in this step.
>
> Use the MCP tools per `.claude/CLAUDE.md`: `mcp__workspace__*` for all file
> operations, and `mcp__tools-py__run_pylint_check`, `run_pytest_check`
> (`extra_args=["-n","auto","-m","not git_integration and not
> claude_cli_integration and not claude_api_integration and not
> formatter_integration and not github_integration and not
> langchain_integration"]`) and `run_mypy_check` after each edit. All three must
> pass before you finish. Produce exactly one commit.
