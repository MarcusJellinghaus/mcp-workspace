# Step 1 — Library prerequisites: `create_issue` assignees, honest `get_available_labels`

## Prompt for LLM

> Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_1.md`)
> only. Follow TDD: write the tests first, watch them fail, then implement.
> Use MCP tools for all file and check operations. One commit at the end.

Two small library changes, both prerequisites for step 3, both in one commit.

---

## WHERE

- `src/mcp_workspace/github_operations/issues/manager.py` — `IssueManager.create_issue` (line ~63)
- `src/mcp_workspace/github_operations/issues/labels_mixin.py` — `get_available_labels` (line ~31)
- `tests/github_operations/issues/test_manager.py` — `TestIssueManagerCore`

## WHAT

```python
@log_function_call
@_handle_github_errors(default_return=create_empty_issue_data())
def create_issue(
    self,
    title: str,
    body: str = "",
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
) -> IssueData:


@log_function_call                       # NOTE: no @_handle_github_errors
def get_available_labels(self: "BaseGitHubManager") -> List[LabelData]:
```

## HOW

### `create_issue`

- Decorators unchanged. The `default_return=create_empty_issue_data()`
  eager-call form is pre-existing here — **leave it**; only genuinely new
  functions use the callable form (see step 2).
- PyGithub's `Repository.create_issue` accepts `assignees: list[str]`, so no
  extra API call is needed.
- Docstring: add the `assignees` arg line, matching the existing style.

### `get_available_labels` — `[]` must stop meaning two things

Today `@_handle_github_errors(default_return=[])` maps a swallowed 404/422/5xx —
and the `repo is None` path — onto the same empty list a repo with no labels
returns. Step 3 validates add-side label names against this list, so the
conflation would turn one transient API failure into
`Error: unknown label(s): bug` — blaming the caller for a typo they did not
make and rejecting every labelled create/edit until the API recovers. Step 6
would render the same failure as `No labels found.`

- **Remove the `@_handle_github_errors(default_return=[])` decorator.** Keep
  `@log_function_call`. Non-auth `GithubException`s now propagate to the caller;
  401/403 already propagated, so that behaviour is unchanged.
- Replace the `if repo is None: … return []` early return with
  `raise ValueError("Could not access repository")`.
- An empty list now means exactly one thing: the repository has no labels.
- Docstring: drop "or empty list on error" from `Returns:`, add a `Raises:`
  section for `ValueError` and `GithubException`.
- This is the only function in `labels_mixin.py` that changes. The neighbouring
  `add_labels` / `remove_labels` keep their decorators — `edit_issue` does not
  compose them (summary §4), so their contract is not this issue's business.

No production caller exists today (`get_available_labels` is only reached from
tests), so the contract change lands with the two new callers in steps 3 and 6
and nothing else to migrate.

## ALGORITHM

`create_issue` — replace the current `if labels: … else: …` branch with a kwargs
dict, so the no-labels call stays byte-identical to today's:

```
kwargs = {"title": title.strip(), "body": body}
if labels:    kwargs["labels"] = labels
if assignees: kwargs["assignees"] = assignees
github_issue = repo.create_issue(**kwargs)
```

Everything else in the function is untouched.

`get_available_labels` — body unchanged apart from the `repo is None` branch:

```
repo = self._get_repository()
if repo is None: raise ValueError("Could not access repository")
# ... existing conversion loop, unchanged
```

## DATA

Unchanged: `IssueData`. `assignees` is already a field on it and is already
populated from `github_issue.assignees` by the existing conversion block.

`get_available_labels` still returns `List[LabelData]`; only the failure
channel changes, from `[]` to a raised exception.

## Tests (TDD)

Add to `TestIssueManagerCore` in `tests/github_operations/issues/test_manager.py`,
reusing the existing `mock_issue_manager` fixture:

1. `test_create_issue_with_assignees` — `assignees=["alice"]` reaches
   `repo.create_issue` as a keyword; result `["assignees"] == ["alice"]`.
2. `test_create_issue_with_labels_and_assignees` — both keywords present in one
   call.
3. `test_create_issue_without_assignees_omits_kwarg` — `assignees` is **not** in
   `repo.create_issue.call_args.kwargs`. This is what protects the two existing
   `assert_called_once_with(...)` tests.

The existing `test_create_issue_success` and `test_create_issue_with_labels`
must still pass unchanged — they assert exact call kwargs.

For `get_available_labels`, in the same class:

4. `test_get_available_labels_api_error_raises` — `repo.get_labels` raises a
   404 `GithubException`; the call now **raises** instead of returning `[]`.
5. `test_get_available_labels_no_repository_raises` — `_get_repository` returns
   `None` → `ValueError`.
6. `test_get_available_labels_empty_repo_returns_empty` — `repo.get_labels`
   returns `[]` → `[]`. This is the test that pins the remaining meaning of the
   empty list.

The existing `test_get_available_labels_success` and
`test_get_available_labels_auth_error_raises` pass unchanged — the latter
already asserts `pytest.raises(GithubException)`.

## Checks

`run_pylint_check`, `run_mypy_check`, then
`run_pytest_check(extra_args=["-n", "auto"], markers=[])` scoped to
`tests/github_operations/`.

## Commit

`Add create_issue assignees and stop get_available_labels swallowing errors`
