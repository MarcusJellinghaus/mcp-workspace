# Step 3 — Route all 18 call sites through `_get_issue_checked`

**Context:** see [summary.md](./summary.md), section "A new validated-fetch
chokepoint on the base manager".

**Goal:** replace every direct `repo.get_issue(` in the issue modules with
`self._get_issue_checked(repo, ...)`. This is the step that actually fixes the
bug. Depends on steps 1 and 2.

---

## WHERE

18 sites across 6 production files. Line numbers are from the pre-change tree —
verify by content, not by number, since earlier edits in the same file shift
them.

| Path | Lines | Note |
|---|---|---|
| `src/mcp_workspace/github_operations/issues/manager.py` | 150, 321, 325, 371, 375 | `get_issue`, `close_issue` ×2, `reopen_issue` ×2 |
| `src/mcp_workspace/github_operations/issues/comments_mixin.py` | 80, 127, 205, 265 | `add_comment`, `get_comments`, `edit_comment`, `delete_comment` |
| `src/mcp_workspace/github_operations/issues/labels_mixin.py` | 102, 106, 162, 166, 218, 222 | `add_labels`, `remove_labels`, `set_labels` — 2 each |
| `src/mcp_workspace/github_operations/issues/events_mixin.py` | 73 | inside a `try/except GithubException` |
| `src/mcp_workspace/github_operations/issues/branch_manager.py` | 313 | `create_remote_branch_for_issue` |
| `src/mcp_workspace/github_operations/_pr_feedback_sources.py` | 134 | module-level function |

Tests: `tests/github_operations/issues/test_manager.py`,
`tests/github_operations/issues/test_labels_mixin.py`,
`tests/github_operations/test_pr_manager_feedback.py` and
`tests/github_operations/test_github_read_tools.py` (four new cases — one read
path, one write path, one inherited path, one rendered-message path).

Docstrings: the same six production files. Every routed public method gains a
`Raises:` entry, and any "or empty … on error" wording in its `Returns:` is
corrected — see "DOCSTRINGS" below.

### Explicitly NOT routed

`src/mcp_workspace/server.py:717` stays a bare `repo.get_issue(number)`. It runs
only after `get_pull(number)` already succeeded, so it resolves in the same
repository by construction. This accepts that "grep for `repo.get_issue(`
returns nothing" is not an available invariant; the invariant is "no bare
`repo.get_issue(` **in the issue modules**".

---

## WHAT

No new functions. Each site becomes:

```python
github_issue = self._get_issue_checked(repo, issue_number)
```

`_pr_feedback_sources.py:134` is a module-level function, not a method:

```python
issue = manager._get_issue_checked(repo, pr_number)  # pylint: disable=protected-access
```

matching the existing `# pylint: disable=protected-access` idiom already on
line 130 of that file.

---

## HOW

- **No new imports in the mixins.** `LabelsMixin`, `CommentsMixin` and
  `EventsMixin` already annotate `self: "BaseGitHubManager"` and already import
  `BaseGitHubManager` from `..base_manager`, so `self._get_issue_checked(...)`
  type-checks as-is.
- **No new imports in `manager.py` or `branch_manager.py`** — both are
  `BaseGitHubManager` subclasses.
- **No new import in `_pr_feedback_sources.py`** — `PullRequestManager` inherits
  the method.
- **`events_mixin.py:73`** is wrapped in `try/except GithubException`. Leave that
  wrapper alone: `IssueIdentityMismatchError` is a `ValueError`, so it passes
  straight through.
- **Do not remove the redundant re-fetches** at `manager.py` 325/375 — separate
  issue. And do **not** remove `labels_mixin` 106/166/222: they are
  load-bearing, because `set_labels` / `add_to_labels` / `remove_from_labels`
  only POST/PUT/DELETE to `…/labels` and never refresh the issue object.

---

## ALGORITHM

Per site:

```
locate    github_issue = repo.get_issue(issue_number)
confirm   a local named `repo` from self._get_repository() is in scope
replace   github_issue = self._get_issue_checked(repo, issue_number)
keep      the surrounding None-check, try/except and comments untouched
verify    grep the issue modules: zero bare `repo.get_issue(` remain
```

Final verification: `repo.get_issue(` should match exactly **one** line in
`src/` — `server.py:717`.

---

## DATA

Return types and data structures are unchanged everywhere.
`_get_issue_checked` returns the same PyGithub `Issue` that `repo.get_issue`
returned, so every downstream `IssueData` / `CommentData` / `EventData`
construction is untouched.

The only behavioural change: on a transferred issue these methods now raise
`IssueIdentityMismatchError` instead of returning data for the wrong issue.
Callers that previously received wrong-but-plausible data now see an error —
that is the fix.

Downstream contracts that shift as a consequence, all intended:

- `transition_issue_label` is `@_handle_github_errors(default_return=False)`;
  the decorator re-raises `ValueError`, so the exception propagates and the
  `bool` contract is not preserved. **No code change there.**
- `github_issue_view` renders
  `Error: Issue #72 was transferred to …` via its existing
  `except Exception as e: return f"Error: {e}"`.

---

## DOCSTRINGS

Routing changes the documented contract of every routed public method, so the
docstrings move in the same commit — a docstring that still promises a safe
empty return is the same silent-wrong-answer failure mode this issue is about.

The clearest case is `manager.py:126` `get_issue`, which today has no `Raises:`
section at all and says:

```
Returns:
    IssueData with issue information, or empty IssueData on error
```

That is now false for one error class. It becomes:

```
Returns:
    IssueData with issue information, or empty IssueData when the
    repository is unavailable

Raises:
    IssueIdentityMismatchError: If GitHub returns an issue from another
        repository (the issue was transferred) or with a different number.
```

Apply the same two edits — drop or narrow any blanket "on error" wording in
`Returns:`, add a `Raises:` entry — to each routed public method:

| File | Methods |
|---|---|
| `issues/manager.py` | `get_issue`, `close_issue`, `reopen_issue` |
| `issues/comments_mixin.py` | `add_comment`, `get_comments`, `edit_comment`, `delete_comment` |
| `issues/labels_mixin.py` | `add_labels`, `remove_labels`, `set_labels` |
| `issues/events_mixin.py` | `get_issue_events` |
| `issues/branch_manager.py` | `create_remote_branch_for_issue` |
| `_pr_feedback_sources.py` | `fetch_conversation_comments` |

Two notes:

- `transition_issue_label` (`labels_mixin.py:245`) is not routed directly, but
  it calls `self.get_issue`, so its `-> bool` contract no longer holds on this
  path. Document the raise there too; per the summary it gets **no logic
  change** — the docstring is the only edit it takes.
- Some of these already document `Raises: ValueError` for input validation.
  Add the specific class anyway — `IssueIdentityMismatchError` is a `ValueError`
  subclass, but a caller cannot tell a transfer from a bad issue number without
  it being named.

Docstrings only. No behaviour, no signatures, no examples (per the project
docstring convention).

---

## TESTS (write first)

Four new cases proving the routing is live — one read path, one write path,
one inherited (non-mixin) path, and one covering the rendered message the issue
actually reports.

In `tests/github_operations/issues/test_manager.py`, in the existing class
(keep the `git_integration` marker it inherits):

```python
def test_get_issue_transferred_raises(self, mock_issue_manager: IssueManager) -> None:
    """A transferred issue raises instead of returning the wrong issue."""
    mock_issue_manager._repository.get_issue.return_value = make_mock_issue(
        220, repo_full_name="test/other-repo"
    )
    with pytest.raises(IssueIdentityMismatchError, match="was transferred to"):
        mock_issue_manager.get_issue(72)
```

In `tests/github_operations/issues/test_labels_mixin.py` — the important one,
because writes are the dangerous half:

```python
def test_set_labels_transferred_does_not_write(self, mock_issue_manager: IssueManager) -> None:
    """The guard fires before any label write reaches the other repository."""
    mock_issue = make_mock_issue(220, repo_full_name="test/other-repo")
    mock_issue_manager._repository.get_issue.return_value = mock_issue
    with pytest.raises(IssueIdentityMismatchError):
        mock_issue_manager.set_labels(72, "bug")
    mock_issue.set_labels.assert_not_called()
```

`assert_not_called()` is the assertion that matters — it proves the fetch guard
runs before the write, which is the whole point of the issue.

In `tests/github_operations/test_pr_manager_feedback.py`, in the existing
`TestGetPRFeedback` class (it already carries the `git_integration` marker) —
this is the only routed site outside `issues/`, and the only one that reaches
`_get_issue_checked` by **inheritance** (`PullRequestManager` →
`BaseGitHubManager`) rather than through a mixin, so nothing else covers it:

```python
def test_conversation_comments_transferred_raises(
    self, mock_manager: PullRequestManager
) -> None:
    """The inherited guard fires on the PR-feedback REST fetch too."""
    mock_repo = self._setup_mocks(mock_manager)
    mock_repo.get_issue = Mock(
        return_value=make_mock_issue(220, repo_full_name="test/other-repo")
    )
    with pytest.raises(IssueIdentityMismatchError):
        fetch_conversation_comments(mock_manager, 72)
```

Call `fetch_conversation_comments` **directly** rather than going through
`manager.get_pr_feedback()`: that method already tolerates a failing comment
fetch and degrades to an `[unavailable]` marker (see the existing
`test_conversation_comments_failure`), which would hide whether the guard ran.
Import it with
`from mcp_workspace.github_operations._pr_feedback_sources import fetch_conversation_comments`.

**Fixture prerequisites for this test, all delivered by step 2:** `_setup_mocks`
must set `mock_repo.full_name = "test/repo"` (otherwise `full_name` is a bare
`Mock` and the comparison is meaningless), and its default `mock_issue` must
come from `make_mock_issue` (otherwise the *other* `TestGetPRFeedback` tests
fail on the identity parse rather than this one passing). If either is missing,
go back and finish step 2 — do not weaken the guard.

Finally, in `tests/github_operations/test_github_read_tools.py`, the rendered
message. The `Returns:`/`Raises:` docstring edits above and the "no `Error: `
prefix" decision are only *claims* until something asserts the string a user
actually sees — this is the symptom the issue reports. The file's existing
`github_issue_view` tests (lines 72-144) already patch `IssueManager`
wholesale, so this needs no fixture work from step 2; it is a plain
`side_effect` on the same mock, in the module's function style (no class, no
marker):

```python
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_view_transferred(mock_manager_cls: MagicMock) -> None:
    """A transferred issue renders the transfer target with one Error: prefix."""
    mock_mgr = MagicMock()
    mock_mgr.get_issue.side_effect = IssueIdentityMismatchError(
        "Issue #72 was transferred to MarcusJellinghaus/mcp-workspace#220 "
        "— https://github.com/MarcusJellinghaus/mcp-workspace/issues/220"
    )
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_view(number=72)

    assert result == (
        "Error: Issue #72 was transferred to "
        "MarcusJellinghaus/mcp-workspace#220 "
        "— https://github.com/MarcusJellinghaus/mcp-workspace/issues/220"
    )
```

Assert **equality**, not `in`: the point is that the output carries exactly one
`Error: ` prefix (added by `server.py:614`, not by the exception) and that the
transfer target survives to the user. A substring assertion would pass on
`Error: Error: …` and on the degraded `Error: Issue #72 not found` that the
`server.py:610` liveness check would produce if the exception were ever
swallowed into an empty `IssueData`. Both are exactly the regressions this case
exists to catch.

Import `make_mock_issue` from step 2 — `from .._issue_test_helpers import
make_mock_issue` in the `issues/` test files, `from ._issue_test_helpers import
make_mock_issue` in `test_pr_manager_feedback.py` — and
`IssueIdentityMismatchError` from `mcp_workspace.github_operations` in all four
test files.

---

## CHECKS

```
mcp__tools-py__run_pylint_check
mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
mcp__tools-py__run_pytest_check(extra_args=["-n", "auto"], markers=["git_integration"])
mcp__tools-py__run_mypy_check
mcp__tools-py__run_lint_imports_check
```

The `git_integration` run is **not optional** — the mixin and manager test
classes are marked, so the fast command skips exactly the tests this step
affects. `run_lint_imports_check` confirms no new layer violation.

If any pre-existing test fails here, the cause is almost certainly a mock-issue
site step 2 missed; fix it in the fixture, never by weakening the guard.

---

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`.
>
> Implement step 3: route all 18 `repo.get_issue(` call sites listed in the step
> file through `self._get_issue_checked(repo, ...)`. Leave `server.py:717` as a
> bare `repo.get_issue(` — it is deliberately excluded.
>
> Do not remove the redundant re-fetches at `manager.py` 325/375, and do not
> remove the `labels_mixin` re-fetches at 106/166/222 — the latter are
> load-bearing. Route them all.
>
> Follow TDD: add the four new tests described in the step file first (read
> path in `test_manager.py`, write path in `test_labels_mixin.py`, inherited
> path in `test_pr_manager_feedback.py`, rendered message in
> `test_github_read_tools.py`), watch them fail, then route the call sites.
>
> Also update the docstrings of the routed public methods as described in the
> "DOCSTRINGS" section — in particular `manager.py` `get_issue`, whose
> `Returns:` still claims "or empty IssueData on error". Docstrings only, in
> this same commit.
>
> When done, verify that `repo.get_issue(` matches exactly one line in `src/`
> (`server.py:717`).
>
> Use MCP tools for all file operations. Run `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_pytest_check` **twice** (fast exclusions, then
> `markers=["git_integration"]`), `mcp__tools-py__run_mypy_check` and
> `mcp__tools-py__run_lint_imports_check`. Fix everything before finishing.
> Then run `./tools/format_all.sh` and make exactly one commit.
