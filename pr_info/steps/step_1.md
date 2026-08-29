# Step 1 — `create_issue` gains `assignees`

## Prompt for LLM

> Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_1.md`)
> only. Follow TDD: write the tests first, watch them fail, then implement.
> Use MCP tools for all file and check operations. One commit at the end.

---

## WHERE

- `src/mcp_workspace/github_operations/issues/manager.py` — `IssueManager.create_issue` (line ~63)
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
```

## HOW

- Decorators unchanged. The `default_return=create_empty_issue_data()`
  eager-call form is pre-existing here — **leave it**; only genuinely new
  functions use the callable form (see step 2).
- PyGithub's `Repository.create_issue` accepts `assignees: list[str]`, so no
  extra API call is needed.
- Docstring: add the `assignees` arg line, matching the existing style.

## ALGORITHM

Replace the current `if labels: … else: …` branch with a kwargs dict, so the
no-labels call stays byte-identical to today's:

```
kwargs = {"title": title.strip(), "body": body}
if labels:    kwargs["labels"] = labels
if assignees: kwargs["assignees"] = assignees
github_issue = repo.create_issue(**kwargs)
```

Everything else in the function is untouched.

## DATA

Unchanged: `IssueData`. `assignees` is already a field on it and is already
populated from `github_issue.assignees` by the existing conversion block.

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

## Checks

`run_pylint_check`, `run_mypy_check`, then
`run_pytest_check(extra_args=["-n", "auto"], markers=[])` scoped to
`tests/github_operations/`.

## Commit

`Add assignees parameter to IssueManager.create_issue`
