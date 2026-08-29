# Step 2 — `IssueManager.edit_issue`

## Prompt for LLM

> Read `pr_info/steps/summary.md` (especially "§4 `edit_issue` is one combined
> library function"), then implement this step (`pr_info/steps/step_2.md`) only.
> Follow TDD: write the tests first, watch them fail, then implement.
> Use MCP tools for all file and check operations. One commit at the end.

---

## WHERE

- `src/mcp_workspace/github_operations/issues/manager.py` — new module-private
  `_issue_to_data`, new `IssueManager.edit_issue`
- `tests/github_operations/issues/test_manager_edit_issue.py` — **new file**
- `tests/github_operations/issues/test_manager_integration.py` — extend the
  existing `test_complete_issue_workflow`

## WHAT

```python
def _issue_to_data(github_issue: Issue) -> IssueData:
    """Convert a PyGithub Issue into IssueData."""


@log_function_call
@_handle_github_errors(default_return=create_empty_issue_data)
def edit_issue(
    self,
    issue_number: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
    add_assignees: Optional[List[str]] = None,
    state: Optional[str] = None,
) -> IssueData:
```

## HOW

- `default_return` is the **callable** `create_empty_issue_data`, not
  `create_empty_issue_data()`. The decorator already supports the factory form
  (`list_pull_requests` uses it); the eager form shares one dict instance across
  every failure. Do not copy the eager form from the siblings.
- Add `from github.Issue import Issue` at module top. `manager.py` already
  imports `base_manager`, which imports PyGithub, so this adds no new dependency
  and does not affect the startup-performance test.
- `_issue_to_data` is module-private in `manager.py`, used by `edit_issue` only.
  It exists so this is not an eighth copy of the conversion block. The existing
  seven copies stay untouched.
- `_issue_to_data` does **not** populate `base_branch` — it matches
  `close_issue`'s conversion, not `get_issue`'s.
- Docstring needs the `# noqa: DOC502` comment for `IssueIdentityMismatchError`,
  as the siblings have.

## ALGORITHM

```
validate_issue_number(issue_number)
if state not in (None, "open", "closed"): raise ValueError("Issue state must be 'open' or 'closed'")
repo = self._get_repository();  if repo is None: log + return create_empty_issue_data()
issue = self._get_issue_checked(repo, issue_number)
current = {label.name for label in issue.labels}          # step-1 fetch carries the labels
scalars = {k: v for k, v in (("title", title), ("body", body), ("state", state)) if v is not None}
if scalars:       issue.edit(**scalars)
if add_labels:    issue.add_to_labels(*add_labels)        # varargs, one request
for name in (remove_labels or []):                        # single-label call, so loop
    if name in current: issue.remove_from_labels(name)    # filter kills the 404-on-no-op path
if add_assignees: issue.add_to_assignees(*add_assignees)  # varargs, one request
return _issue_to_data(self._get_issue_checked(repo, issue_number))
```

Two details that are not stylistic:

- `remove_from_labels` takes **one** label (verified against the installed
  PyGithub), unlike `add_to_labels` / `add_to_assignees`.
- The `if name in current` filter is what stops a no-op removal from turning a
  successful title/body edit into a reported failure.

## DATA

Returns `IssueData` — the refetched state, so `labels` and `assignees` are the
resulting sets, which is what the tool reports. Empty `IssueData`
(`number == 0`) on swallowed failure.

Raises `ValueError` for a bad issue number or a bad `state`; the decorator
re-raises it.

## Tests (TDD)

New `tests/github_operations/issues/test_manager_edit_issue.py`, mocked, reusing
the `mock_issue_manager` fixture from `tests/github_operations/issues/conftest.py`:

1. Scalars only — `issue.edit(title=..., body=...)` called once; no label or
   assignee call.
2. No arguments at all — `issue.edit` **not** called; still returns refetched data.
3. `state="closed"` — passed inside the same single `edit()` call as title/body.
4. `state="bogus"` — raises `ValueError`.
5. `add_labels=["a","b"]` — `add_to_labels("a","b")` called once.
6. `remove_labels` where one label is present and one absent — `remove_from_labels`
   called **once**, with the present one only.
7. `remove_labels` where none are present — `remove_from_labels` never called,
   result still non-empty.
8. `add_assignees=["alice"]` — `add_to_assignees("alice")` called once.
9. Call-count guard — `_get_issue_checked` called exactly twice for a call that
   touches scalars + labels + assignees.
10. Invalid issue number raises `ValueError`.
11. Swallowed `GithubException` (e.g. 422) returns `number == 0`.
12. Two consecutive failures return **distinct** dict objects — this is what the
    callable `default_return` buys.

Integration — extend the existing
`test_manager_integration.py::test_complete_issue_workflow`, which already
creates exactly one issue and closes it in a `finally`. Add a section calling
`edit_issue` for title + label add + label remove + assignee, asserting the
returned label set. No new file, no new fixture, no extra real issue.

## Checks

`run_pylint_check`, `run_mypy_check`, then `run_pytest_check` on
`tests/github_operations/` (the integration test skips without a token).

## Commit

`Add IssueManager.edit_issue combined edit function`
