# Step 1 — `SubIssuesMixin`, composed into `IssueManager`

Read [summary.md](./summary.md) first. This step adds the whole manager-layer
surface plus the dependency floor it requires. No `server.py` change.

## WHERE

Created:

- `src/mcp_workspace/github_operations/issues/sub_issues_mixin.py`
- `tests/github_operations/issues/test_sub_issues_mixin.py`

Modified:

- `src/mcp_workspace/github_operations/issues/manager.py`
- `pyproject.toml`

## WHAT

Module-level in `sub_issues_mixin.py`:

```python
def sub_issue_total(issue: Issue) -> Optional[int]
def _fetch_issue(manager: BaseGitHubManager, repo: Repository, number: int) -> Issue
def _write_link(
    manager: BaseGitHubManager,
    parent_number: int,
    child_number: int,
    unlink: bool,
) -> Optional[Issue]
```

On `class SubIssuesMixin:` — each method annotates `self: "BaseGitHubManager"`,
as `comments_mixin.py` does:

```python
def add_sub_issue(self, parent_number: int, child_number: int) -> Optional[Issue]
def remove_sub_issue(self, parent_number: int, child_number: int) -> Optional[Issue]
def list_sub_issues(self, parent_number: int, max_results: int = 30) -> Optional[List[SubIssue]]
```

`__all__ = ["SubIssuesMixin", "sub_issue_total"]`.

## HOW

Imports in `sub_issues_mixin.py`:

```python
from __future__ import annotations

import logging
from itertools import islice
from typing import List, Optional, cast

from github.Issue import Issue, SubIssue          # SubIssue is defined in github/Issue.py
from github.Repository import Repository
from github.SubIssueSummary import SubIssueSummary
from mcp_coder_utils.log_utils import log_function_call

from ..base_manager import BaseGitHubManager
from .base import validate_issue_number
```

- `@log_function_call` on each of the three public methods.
- **No `@_handle_github_errors`** — do not import it. Put a comment above the
  class stating that the decorator (`base_manager.py:78`) swallows every
  non-401/403 `GithubException`, which would discard the 404/422 text the tools
  must surface, so `GithubException` propagates to the server layer instead.
- The shared logic is module-level functions taking `manager`, **not** private
  methods on the mixin: mixin methods are typed `self: "BaseGitHubManager"` and
  that class does not declare these helpers, so `self._write_link(...)` fails
  mypy.
- `manager._get_repository()` and `manager._get_issue_checked(...)` are private;
  add `# pylint: disable=protected-access` where pylint complains, matching the
  existing usage style in `server.py:843`/`856`.

`manager.py` — add to the imports and the bases:

```python
from .sub_issues_mixin import SubIssuesMixin

class IssueManager(
    CommentsMixin, LabelsMixin, EventsMixin, SubIssuesMixin, BaseGitHubManager
):
```

`pyproject.toml:30` — `"PyGithub>=2.1.0",` → `"PyGithub>=2.7.0",`. 2.7.0 is the
release that added sub-issue support; see summary.

## ALGORITHM

```
sub_issue_total(issue):
    summary = cast(Optional[SubIssueSummary], issue.sub_issues_summary)
    return None if summary is None else summary.total

_fetch_issue(manager, repo, number):
    issue = manager._get_issue_checked(repo, number)      # transferred-issue guard
    if issue.pull_request is not None:
        raise ValueError(f"#{number} is a pull request, not an issue")
    return issue

_write_link(manager, parent_number, child_number, unlink):
    validate_issue_number(parent_number); validate_issue_number(child_number)
    repo = manager._get_repository()
    if repo is None: log error; return None
    parent = _fetch_issue(manager, repo, parent_number)
    child = _fetch_issue(manager, repo, child_number)     # fetched for the guard AND for .id
    parent.remove_sub_issue(child) if unlink else parent.add_sub_issue(child)
    return manager._get_issue_checked(repo, parent_number)  # refetch: post-write summary

list_sub_issues(parent_number, max_results=30):
    validate_issue_number(parent_number)
    repo = manager._get_repository(); if None: return None
    parent = _fetch_issue(self, repo, parent_number)
    return list(islice(parent.get_sub_issues(), max(0, max_results)))
```

`add_sub_issue` / `remove_sub_issue` are one line each:
`return _write_link(self, parent_number, child_number, unlink=False)` (resp.
`True`). Pass the child **object** — PyGithub reads `.id` off it, and the API
takes the internal id, not the issue number.

## DATA

- `sub_issue_total` → `Optional[int]`; `None` when the payload carried no
  summary.
- `add_sub_issue` / `remove_sub_issue` → `Optional[Issue]`, the **refetched**
  parent; `None` means the repository was inaccessible.
- `list_sub_issues` → `Optional[List[SubIssue]]`; `None` means inaccessible
  repository, `[]` means no sub-issues. Keeping those distinct is what lets the
  server render `_repo_access_error` instead of "No sub-issues."
- Both PyGithub write wrappers return a `SubIssue`; it is discarded, since the
  refetched parent carries the count the tools report.
- Raises: `ValueError` from `validate_issue_number` and from the PR guard;
  `IssueIdentityMismatchError` (a `ValueError`) from `_get_issue_checked`;
  `GithubException` straight from the API.

## Tests (write first)

`tests/github_operations/issues/test_sub_issues_mixin.py`, modelled on
`tests/github_operations/issues/test_comments_mixin.py`: `@pytest.mark.git_integration`
on the class, the `mock_issue_manager` fixture from
`tests/github_operations/conftest.py` (drive the API through
`mock_issue_manager._repository.get_issue`), and `make_mock_issue` from
`tests/github_operations/_issue_test_helpers.py`.

Note `make_mock_issue` returns a `MagicMock`, so `mock_issue.pull_request` is a
truthy Mock by default — set `pull_request = None` on any issue that should pass
the guard.

`_write_link` fetches three times, in this order: parent, child, then the
refetched parent. Drive it with an explicit `side_effect` list rather than
`return_value`:

```python
mock_issue_manager._repository.get_issue.side_effect = [
    mock_parent, mock_child, mock_refetched_parent
]
```

`mock_refetched_parent` is a distinct object (`make_mock_issue(3)` with its own
`sub_issues_summary`), so "the refetched parent is what comes back" is assertable
by identity. `list_sub_issues` fetches once, so it needs a single-element
`side_effect` or a plain `return_value`.

Cover:

1. `add_sub_issue` success — `mock_parent.add_sub_issue.assert_called_once_with(mock_child)`
   (the child **object**), and `result is mock_refetched_parent`, not
   `mock_parent`.
2. `remove_sub_issue` success — `mock_parent.remove_sub_issue.assert_called_once_with(mock_child)`,
   and again `result is mock_refetched_parent`.
3. `list_sub_issues` returns the children in order.
4. `list_sub_issues` honours `max_results` — pass more children than the cap and
   assert the slice length; `max_results=0` and a negative value both yield `[]`.
5. Parent is a PR → `ValueError` matching `is a pull request`.
6. Child is a PR → same, and assert `add_sub_issue` was never called.
7. `validate_issue_number` rejection — `0` and `-1` raise `ValueError`.
8. Repository inaccessible (`_get_repository` patched to return `None`) → all
   three return `None`.
9. **`GithubException` propagates** out of `add_sub_issue` — a 422 with
   `{"message": "Issue may not contain duplicate sub-issues..."}` must escape,
   not be swallowed. This is the test that pins the missing decorator.
10. `sub_issue_total` with a real `None` — build an object whose
    `sub_issues_summary` is literally `None` (a `MagicMock` auto-creates a Mock
    for any attribute and so cannot catch this) and assert `None`. Plus a case
    with a stub exposing `total = 3` asserting `3`.

## Checks

`run_format_code`, then pylint, pytest `-n auto`, mypy, vulture, ruff,
lint-imports. Mypy is the one to watch: it is what the `cast` in
`sub_issue_total` exists for.

## Commit

`feat(issues): add SubIssuesMixin for native sub-issue links (#294)`

## LLM prompt

> Implement Step 1 of the sub-issue tools feature for issue #294.
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md` in full first.
> Work test-first: write `tests/github_operations/issues/test_sub_issues_mixin.py`
> covering the ten cases listed in step_1, then create
> `src/mcp_workspace/github_operations/issues/sub_issues_mixin.py`, compose
> `SubIssuesMixin` into `IssueManager` in `issues/manager.py`, and raise the
> `PyGithub` floor to `>=2.7.0` in `pyproject.toml`.
> Do not add `@_handle_github_errors` to the mixin methods — summary.md explains
> why, and case 9 tests it. Do not touch `issues/types.py`, `issues/__init__.py`
> or `server.py` in this step.
> Then run `run_format_code` followed by pylint, pytest (`extra_args=["-n","auto"]`),
> mypy, vulture, ruff and lint-imports, fix anything they report, and make one
> commit.
