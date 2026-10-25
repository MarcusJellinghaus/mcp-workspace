# Step 1 — Add `PullRequestManager.update_pull_request` (TDD)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_1.md`).
> Write the tests first (they fail), then add the method so they pass.
> Run pylint, mypy, and pytest (`extra_args: ["-n", "auto"]`); all must pass.
> Run `run_format_code`, then make exactly one commit.

## Precondition

`tests/github_operations/test_pr_manager_add_assignees.py` must still use
`@pytest.mark.git_integration` and patch `mcp_workspace.github_operations._client.Github`
plus `mcp_workspace.github_operations.base_manager.get_github_token`.
If it doesn't, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- Create: `tests/github_operations/test_pr_manager_update_pull_request.py`
- Modify: `src/mcp_workspace/github_operations/pr_manager.py`. Add the method
  directly after `close_pull_request`, and add `Any` to the `typing` import.

## WHAT

```python
@log_function_call
@_handle_github_errors(cast(PullRequestData, {}))
def update_pull_request(
    self,
    pr_number: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
) -> PullRequestData:
```

Docstring (Google style, like the neighbouring methods):
- Args: `title`/`body` — `None` = unchanged; `body=""` clears the description; title is stripped.
- Returns: updated `PullRequestData`. When both are `None`, the current PR data. Empty dict on failure.
- Raises: `ValueError` if a supplied title is empty after stripping.

## HOW

- Decorators as shown above (identical to `close_pull_request`).
- Reuses `self._validate_pr_number`, `self._get_repository`, module-level `_pr_to_data`.
- `fields` is typed `dict[str, Any]`, because mypy can't check a `**` unpacking against
  PyGithub's per-keyword `edit()` types (same reason as `edit_issue`).

## ALGORITHM

```
if title is not None and not title.strip(): raise ValueError("Pull request title cannot be empty")
if not _validate_pr_number(pr_number) or (repo := _get_repository()) is None: return {}
pr = repo.get_pull(pr_number)
fields = {}; if title is not None: fields["title"] = title.strip(); if body is not None: fields["body"] = body
if not fields: return _pr_to_data(pr)
pr.edit(**fields); return _pr_to_data(repo.get_pull(pr_number))
```

Write the PR-number and repo checks as two separate `if` blocks, like `close_pull_request`.
The walrus above is only shorthand.

## DATA

- Returns `PullRequestData` (existing TypedDict in `pr_types.py`) built by `_pr_to_data`.
- `{}` (cast to `PullRequestData`) for an invalid number, missing repo, or non-auth `GithubException`.

## Tests — `test_pr_manager_update_pull_request.py`

Module docstring, `@pytest.mark.git_integration` class `TestUpdatePullRequest`.

**Fixture** `manager_and_repo(tmp_path)`:
1. Run `git.Repo.init(tmp_path / "git_dir")` and add the remote `https://github.com/testowner/testrepo.git`.
2. Patch `mcp_workspace.github_operations._client.Github` so that `get_repo` returns a `MagicMock` `mock_repo`.
3. Patch `base_manager.get_github_token` to return `"dummy-token"`.
4. Yield `(PullRequestManager(git_dir), mock_repo)` while the patches are active.

Each test sets `mock_repo.get_pull.return_value = create_mock_pr(...)` (from `._pr_test_helpers`),
with the expected post-edit title/body.

1. **`test_update_fields`**, parametrized with `(title, body, expected_kwargs, expected_title, expected_body)`:
   - title only: `"  New  "`, `None` → `{"title": "New"}`
   - body only: `None`, `"New body"` → `{"body": "New body"}`
   - both: `"New"`, `"New body"` → `{"title": "New", "body": "New body"}`
   - clear body: `None`, `""` → `{"body": ""}`

   Assert:
   - `mock_pr.edit.assert_called_once_with(**expected_kwargs)`
   - `mock_repo.get_pull.call_count == 2`
   - `result["title"]` and `result["body"]` match the expected values
2. **`test_update_neither_field`**:
   - Call `update_pull_request(123)`.
   - Assert `edit.assert_not_called()`, `get_pull.call_count == 1`, and `result["number"] == 123`.
3. **`test_update_blank_title_raises`**:
   - Run `update_pull_request(123, title="   ")` inside `pytest.raises(ValueError, match="cannot be empty")`.
   - Assert `get_pull.assert_not_called()`.
4. **`test_update_invalid_pr_number`**:
   - Call `update_pull_request(0, title="New")`.
   - Assert `not result` and `get_pull.assert_not_called()`.
5. **`test_update_api_error`**:
   - Set `get_pull.side_effect = GithubException(404, {"message": "Not Found"}, None)`.
   - Call `update_pull_request(123, title="New")`.
   - Assert `not result`.

## Commit

`feat(pr): add PullRequestManager.update_pull_request for title/body (#349)`
