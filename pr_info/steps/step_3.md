# Step 3 — `LabelsMixin.get_issue_for_status`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 3** exactly as described
> in `pr_info/steps/step_3.md`. Write the tests first, then the code. Run pylint,
> pytest (`-n auto`) and mypy via the MCP tools until all pass, format the code,
> and make exactly one commit.

## WHERE

- `src/mcp_workspace/github_operations/issues/labels_mixin.py`
- `tests/github_operations/issues/test_labels_mixin.py`

## WHAT

```python
@log_function_call
def get_issue_for_status(self: BaseGitHubManager, issue_number: int) -> IssueData: ...
```

## HOW

- **Not** decorated with `_handle_github_errors`. Add a comment explaining why,
  with the same reasoning as in `sub_issues_mixin.py`: a swallowed 404/5xx
  would come back as an empty `number == 0` result.
- Reuse `validate_issue_number`, `self._get_repository()`,
  `self._get_issue_checked(repo, n)` and `issue_to_data`. Do not call
  `get_issue`, which runs the base-branch trust lookup.
- The PR check follows `sub_issues_mixin._fetch_issue`:
  `issue.pull_request is not None` → `ValueError(f"#{n} is a pull request, not an issue")`.
- If the repository is unavailable, raise `ValueError("Could not access repository")`,
  as `get_available_labels` does. An empty result is never returned.

## ALGORITHM

```
validate_issue_number(issue_number)
repo = self._get_repository(); if repo is None: raise ValueError("Could not access repository")
issue = self._get_issue_checked(repo, issue_number)
if issue.pull_request is not None: raise ValueError("#N is a pull request, not an issue")
return issue_to_data(issue)
```

## DATA

Returns `IssueData`. The callers use `number`, `state`, `labels` and `url`.

## Tests (write first; use the `mock_issue_manager` fixture)

- open issue → `IssueData` with its labels and state, one `get_issue` call on the repo
- closed issue → returned with `state == "closed"`
- `pull_request` set → `ValueError` containing "is a pull request"
- `GithubException(404)` from `repo.get_issue` → propagates unchanged
- invalid number (0) → `ValueError`
