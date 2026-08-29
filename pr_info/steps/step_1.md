# Step 1 — `reference_name` on the four GitHub read tools

One commit: tests + implementation + checks passing.
Read [summary.md](./summary.md) first, in particular design decisions 1–3.

## WHERE

| File | Change |
|---|---|
| `tests/github_operations/test_github_read_tools.py` | New fixture + 6 tests (write first) |
| `src/mcp_workspace/server_reference_tools.py` | New `get_reference_repo_url()` |
| `src/mcp_workspace/server.py` | New `_issue_manager()`; `reference_name` on four tools |

## WHAT

### `server_reference_tools.py`

```python
def get_reference_repo_url(name: str) -> str:
    """Resolve a reference project name to its configured repository URL.

    Synchronous and side-effect free — unlike get_reference_project_path(),
    this never calls ensure_available(), so it never clones.

    Returns:
        The configured repository URL.

    Raises:
        ValueError: If no reference project with the given name exists, or
            the project has no URL configured.
    """
```

Place it next to `get_reference_project_path()`. Do **not** register it as an MCP tool.

### `server.py`

```python
def _issue_manager(reference_name: Optional[str]) -> "IssueManager":
    """Build an IssueManager for the workspace repo or a reference project."""
```

Private module-level helper, placed above `github_issue_view`. No `@mcp.tool()`, no
`@log_function_call`.

Then add `reference_name: Optional[str] = None` as the **last** parameter of
`github_issue_view`, `github_issue_list`, `github_pr_view` and `github_search`, and replace
each `manager = IssueManager(project_dir=_project_dir)` with
`manager = _issue_manager(reference_name)`.

## HOW

- **Typing:** add `TYPE_CHECKING` to the existing `from typing import ...` line in `server.py`
  and add, next to the other module-level imports:

  ```python
  if TYPE_CHECKING:
      from mcp_workspace.github_operations.issues import IssueManager
  ```

  This does not execute at runtime, so `tests/test_startup_performance.py` (which asserts that
  importing `mcp_workspace.server` does not eagerly import `github`/`git`) still passes.

- **Lazy import stays:** `_issue_manager()` does the real
  `from mcp_workspace.github_operations.issues import IssueManager` **inside the function
  body**. This keeps PyGithub off the startup path (`docs/ARCHITECTURE.md` §4) and keeps the
  existing `@patch("mcp_workspace.github_operations.issues.IssueManager")` tests working,
  because the patched module attribute is still what gets looked up at call time.

- **Delete the now-redundant imports:** all four tool bodies currently import `IssueManager`
  themselves. Remove those four lines. `github_pr_view` keeps its `formatters` and `CommentData`
  imports; `github_issue_view`, `github_issue_list` and `github_search` keep their `formatters`
  imports.

- **Import the accessor** in `server.py` from the existing
  `from mcp_workspace.server_reference_tools import (...)` block.

- **No new error handling.** `_issue_manager()` raises `ValueError`; the construction already
  sits as the first statement inside each tool's `try:`, so the existing
  `except Exception as e: return f"Error: {e}"` produces the required error string
  (decision 3).

- **Docstrings:** add a `reference_name` entry to each tool's `Args:` block — this text is the
  MCP tool description callers see. Suggested wording:

  > `reference_name: Optional reference project name. When set, reads from that project's GitHub repository instead of the workspace repository.`

- **`github_search` prose must change too, not just its `Args:` block.** Two lines currently
  assert the tool is workspace-only and would contradict the new parameter:

  - the summary line (`server.py:746`): `"""Search GitHub issues and pull requests in this repository.`
  - the body note (`server.py:748`): `Automatically scoped to current repository. Additional qualifiers ...`

  Rewrite both so the description states the scope is a single repository — the workspace repo
  by default, or the reference project named by `reference_name`. Suggested wording:

  > `"""Search GitHub issues and pull requests in a single repository.`
  >
  > `Scoped to the workspace repository, or to the reference project named by reference_name. Additional qualifiers can be included inline in the query string (e.g., "fix login author:marcus").`

  The other three tools' summary lines make no repository claim and need only the `Args:` entry.

## ALGORITHM

```
get_reference_repo_url(name):
    if name not in _reference_projects:      raise ValueError(f"Reference project '{name}' not found")
    url = _reference_projects[name].url
    if url is None:                          raise ValueError(f"Reference project '{name}' has no URL configured")
    return url

_issue_manager(reference_name):
    import IssueManager                       # lazy, inside the body
    if reference_name is None:                return IssueManager(project_dir=_project_dir)
    return IssueManager(repo_url=get_reference_repo_url(reference_name))
```

No `_project_dir is None` guard: today that surfaces as
`"Error: Exactly one of project_dir or repo_url must be provided"` from
`BaseGitHubManager.__init__`, and preserving it keeps the no-reference path unchanged.

## DATA

- `get_reference_repo_url` → `str` (e.g. `"https://github.com/MarcusJellinghaus/mcp_coder"`).
  Raises `ValueError` with one of two exact messages:
  `"Reference project '<name>' not found"` /
  `"Reference project '<name>' has no URL configured"`.
- `_issue_manager` → `IssueManager`. Raises `ValueError` (propagated from the accessor or from
  `BaseGitHubManager.__init__`, e.g. `"Invalid GitHub repository URL: ..."`).
- The four tools keep returning `str` — formatted output or `"Error: ..."`.

## TESTS (write first)

All in `tests/github_operations/test_github_read_tools.py`, alongside the existing
`@patch("mcp_workspace.github_operations.issues.IssueManager")` tests.

Fixture — note the paths deliberately do not exist, which proves the feature needs no working
tree:

```python
@pytest.fixture
def reference_projects() -> Generator[None, None, None]:
    set_reference_projects({
        "sibling": ReferenceProject(
            name="sibling",
            path=Path("/does/not/exist"),
            url="https://github.com/owner/sibling",
        ),
        "nourl": ReferenceProject(name="nourl", path=Path("/does/not/exist/2"), url=None),
    })
    yield
    set_reference_projects({})
```

A module-level helper configures one mock manager well enough for all four tools, so the
parametrized test can assert construction without caring about formatting:

```python
def _configure_manager(mock_mgr: MagicMock) -> None:
    """Set up a mock IssueManager that satisfies all four read tools."""
    # get_issue -> _make_issue(), get_comments -> [], list_issues -> [],
    # _get_repository -> MagicMock(full_name="owner/sibling"),
    # _github_client.search_issues -> []
```

Tests:

1. `test_reference_name_uses_repo_url` — parametrized over all four tools
   (`(callable, kwargs)` pairs: `(github_issue_view, {"number": 42})`,
   `(github_issue_list, {})`, `(github_pr_view, {"number": 10})`,
   `(github_search, {"query": "x"})`). Call with `reference_name="sibling"`; assert
   `mock_manager_cls.call_args.kwargs == {"repo_url": "https://github.com/owner/sibling"}`.
   This is the wiring that could be forgotten at one of four sites, so it is worth the
   parametrization.
2. `test_no_reference_name_uses_project_dir` — one tool, no `reference_name`; assert
   `call_args.kwargs == {"project_dir": project_dir}`.
3. `test_unknown_reference_name_returns_error` — parametrized over the four tools with
   `reference_name="nope"`; assert the result is exactly
   `"Error: Reference project 'nope' not found"` and `mock_manager_cls.assert_not_called()`.
4. `test_reference_project_without_url_returns_error` — one tool with
   `reference_name="nourl"`; assert
   `"Error: Reference project 'nourl' has no URL configured"`.
5. `test_reference_read_does_not_clone` — patch
   `mcp_workspace.server_reference_tools.ensure_available`, call one tool with
   `reference_name="sibling"`, assert it was not called. This is the regression guard for
   design decision 1 and the reason a plain path lookup was rejected.
6. `test_reference_name_scopes_search_query` — the one behavioural assertion, not a
   construction one: call `github_search(query="x", reference_name="sibling")` and assert the
   query passed to `manager._github_client.search_issues` starts with `repo:owner/sibling`
   (`mock_mgr._github_client.search_issues.call_args.kwargs["query"]`). `_configure_manager`
   already sets `_get_repository() -> MagicMock(full_name="owner/sibling")`, so this covers
   the claim that `github_search` needs no special handling in `repo_url` mode.

Imports the test file needs on top of what it already has: `set_reference_projects` from
`mcp_workspace.server_reference_tools`, `ReferenceProject` from
`mcp_workspace.reference_projects`.

No separate unit test for `get_reference_repo_url`: both of its error paths and its happy path
are asserted through the tools, which is where the `"Error: ..."` contract actually lives.

## LLM PROMPT

```
Implement step 1 of pr_info/steps/summary.md, specified in pr_info/steps/step_1.md.

Read pr_info/steps/summary.md (especially design decisions 1-3) and pr_info/steps/step_1.md
in full before starting.

Work test-first:
1. Add the fixture, the _configure_manager helper and the six tests described under TESTS to
   tests/github_operations/test_github_read_tools.py. Run pytest and confirm they fail.
2. Add get_reference_repo_url() to src/mcp_workspace/server_reference_tools.py.
3. Add _issue_manager() to src/mcp_workspace/server.py, add reference_name as the last
   parameter of github_issue_view, github_issue_list, github_pr_view and github_search,
   swap the four IssueManager constructions to _issue_manager(reference_name), delete the
   four now-redundant lazy IssueManager imports, and document reference_name in each
   Args: block. Also rewrite github_search's summary line and its "Automatically scoped
   to current repository" note, which currently contradict the new parameter.
4. Run pytest, pylint and mypy until all pass. Do not change any behaviour when
   reference_name is omitted, and do not touch anything under github_operations/.

Then run mcp__mcp-tools-py__run_format_code and make exactly one commit.
```

## DONE WHEN

- All six new tests pass; every pre-existing test in the file still passes unchanged.
- No tool docstring still claims the GitHub read tools are limited to the current repository —
  in particular `github_search`'s summary line and its scoping note.
- pylint, pytest and mypy are green.
- `git diff` shows no changes under `src/mcp_workspace/github_operations/`.
