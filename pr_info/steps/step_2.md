# Step 2 — Add `PullRequestManager.add_assignees()` + tests

> Read `pr_info/steps/summary.md` first, and note Step 1 already added `_pr_to_data`
> and the `assignees` field. This step adds the new public method and its dedicated
> test file. One commit.

## WHERE

- Modify: `src/mcp_workspace/github_operations/pr_manager.py` (add one method)
- Create: `tests/github_operations/test_pr_manager_add_assignees.py`

## WHAT

```python
def add_assignees(self, pr_number: int, *logins: str) -> PullRequestData:
    """Add one or more assignees to an existing pull request.

    Wraps PyGithub's PullRequest.add_to_assignees(*logins) on the authenticated
    PyGithub path. Returns the updated PullRequestData.

    Note: GitHub silently drops logins that are not assignable (not a collaborator /
    no repo access) — add_to_assignees succeeds with no error and no effect, so a
    non-empty return is not proof the user was actually assigned. Intended for
    best-effort use.
    """
```

## HOW (integration points)

- Decorators, matching the other write methods:
  ```python
  @log_function_call
  @_handle_github_errors(lambda: cast(PullRequestData, {}))
  def add_assignees(self, pr_number: int, *logins: str) -> PullRequestData:
  ```
- Reuses `_validate_pr_number`, `_get_repository`, and `_pr_to_data` from Step 1.
- No `__init__.py` change (method on the already-exported `PullRequestManager`).

## ALGORITHM (core logic — single code path)

```
if not _validate_pr_number(pr_number):  return cast(PullRequestData, {})
repo = _get_repository()
if repo is None:                        return cast(PullRequestData, {})
pr = repo.get_pull(pr_number)
if logins:                              # empty *logins -> no API write (no-op)
    pr.add_to_assignees(*logins)        # mutates pr.assignees in place
return _pr_to_data(pr)                  # single fetch, reuse same object
```

## DATA

- Returns `PullRequestData` with `assignees` reflecting the (mutated) live object.
- Invalid `pr_number`, missing repo, or `GithubException` → `{}`
  (validation / decorator).

## Tests (`test_pr_manager_add_assignees.py`)

Follow `test_pr_manager_find_by_head.py`: git-init `tmp_path` with a GitHub remote,
`@patch("mcp_workspace.github_operations._client.Github")`, patch
`mcp_workspace.github_operations.base_manager.get_github_token`, reuse `create_mock_pr`,
class marked `@pytest.mark.git_integration`.

Cases:
1. **Happy path** — `mock_repo.get_pull.return_value = create_mock_pr(assignees=[MagicMock(login="alice")])`;
   call `add_assignees(123, "alice")`; assert `mock_pr.add_to_assignees.assert_called_once_with("alice")`
   and `result["assignees"] == ["alice"]`.
2. **Multiple logins** — `add_assignees(123, "alice", "bob")`; assert
   `add_to_assignees` called once with `("alice", "bob")`.
3. **Empty logins** — `add_assignees(123)`; assert `mock_pr.add_to_assignees.assert_not_called()`
   and result is the current PR data (`result["number"] == 123`).
4. **Invalid `pr_number`** — `add_assignees(0, "alice")` (or `-1`); assert `result == {}`
   and `get_pull` not called.
5. **`GithubException`** — `mock_repo.get_pull.side_effect = GithubException(500, {"message": "..."}, None)`;
   assert `result == {}`.

## Checks (MCP tools, after each edit)

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_pytest_check` with `extra_args=["-n", "auto"]`, `markers=["git_integration"]`
- `mcp__tools-py__run_mypy_check`

## Commit

One commit: `add_assignees` method + new test file, all checks passing.

## LLM Prompt

> Implement Step 2 from `pr_info/steps/step_2.md` (context: `pr_info/steps/summary.md`;
> Step 1 already added `_pr_to_data` and the `assignees` field). In
> `src/mcp_workspace/github_operations/pr_manager.py`, add
> `add_assignees(self, pr_number: int, *logins: str) -> PullRequestData` with decorators
> `@log_function_call` and `@_handle_github_errors(lambda: cast(PullRequestData, {}))`.
> Body: validate `pr_number` (else `{}`), get repo (else `{}`), `pr = repo.get_pull(pr_number)`,
> then `if logins: pr.add_to_assignees(*logins)`, and `return _pr_to_data(pr)` — a single
> fetch, one code path, no re-fetch. Document that GitHub silently drops non-assignable
> logins (best-effort). Create `tests/github_operations/test_pr_manager_add_assignees.py`
> following `test_pr_manager_find_by_head.py`, reusing `create_mock_pr`, with the five
> cases in the step (happy path, multiple logins, empty logins no-op, invalid number,
> GithubException). Use only MCP file tools. After edits run pylint, pytest
> (`-n auto`, marker `git_integration`), and mypy; fix until green.
