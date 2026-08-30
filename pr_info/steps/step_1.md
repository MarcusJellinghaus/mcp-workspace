# Step 1 — `github_label_list` gains `reference_name`

Read [summary.md](./summary.md) first.

The cheapest and least contentious part of #272, and a prerequisite for the rest: without
cross-repo label listing, a caller writing to a sibling repo hits `Error: unknown label(s): …`
with no way to discover what that repository defines. This step also creates the test module
that steps 2-4 extend.

## WHERE

- `src/mcp_workspace/server.py` — `github_label_list` (`:1355-1392`)
- `tests/github_operations/test_github_write_tools_reference.py` — **new file**

## WHAT

```python
@mcp.tool()
@log_function_call
def github_label_list(
    search: Optional[str] = None,
    reference_name: Optional[str] = None,
) -> str:
```

Test module skeleton (grown by later steps):

```python
_TOOL_CASES: list[tuple[Callable[..., str], dict[str, Any]]] = [
    (github_label_list, {}),
]
_TOOL_IDS = ["label_list"]

def _make_manager() -> MagicMock: ...
```

## HOW

- Body change is two lines: delete the local
  `from mcp_workspace.github_operations.issues import IssueManager` (`:1369-1370`, comment
  included) and replace `manager = IssueManager(project_dir=_project_dir)` (`:1373`) with
  `manager = _issue_manager(reference_name)`.
- `_issue_manager` is already defined at `server.py:744` and does the lazy import itself.
  Nothing else in the function changes; the existing `except Exception: return f"Error: {e}"`
  turns `_issue_manager`'s `ValueError` into the same error strings the read tools return.
- Tool stays `def`, not `async def`.
- Docstring: relax `:1358` from "the repository" to "the workspace repository or a reference
  project", and add under `Args:`

  ```
  reference_name: Optional reference project name. When set, lists the labels
      of that project's GitHub repository instead of the workspace repository.
  ```

- Test module mirrors `tests/github_operations/test_github_read_tools_reference.py`: module
  docstring scoping it to the write/label tools, `pytestmark = pytest.mark.usefixtures("setup_server")`,
  and a `reference_projects` fixture with **deliberately non-existent paths** (a GitHub call
  must resolve through the configured URL and never touch a working tree). Do **not** extend
  `test_github_read_tools_reference.py`, whose docstring scopes it to read-only tools, and do
  **not** put helpers in `_github_read_tools_helpers.py`, which is read-shaped.
- Patch target for every test: `@patch("mcp_workspace.github_operations.issues.IssueManager")` —
  the module `_issue_manager` imports from at call time, and the target the three existing
  write-tool test modules already use.

## ALGORITHM

```
github_label_list(search, reference_name):
    try:
        manager = _issue_manager(reference_name)      # ValueError -> "Error: ..."
        labels  = manager.get_available_labels()
        filter by `search` on name/description (unchanged)
        render lines / "No labels found." (unchanged)
    except Exception as e: return f"Error: {e}"
```

## DATA

Return value unchanged: one `"<name>  #<color>  <description>"` line per label,
`"No labels found."`, or `"Error: ..."`.

`_make_manager()` returns a `MagicMock` whose `get_available_labels` returns a list of
LabelData-shaped dicts (`{"name", "color", "description", "url"}`). Later steps extend it with
`add_comment`, `create_issue`, `edit_issue`, `get_issue` and `_github_client.get_user().login`.

## Tests (write first)

In the new module:

1. `test_reference_name_uses_repo_url` — parametrized over `_TOOL_CASES`;
   `mock_manager_cls.call_args.kwargs == {"repo_url": "https://github.com/owner/sibling"}`.
2. `test_no_reference_name_uses_project_dir` — parametrized; `== {"project_dir": project_dir}`.
3. `test_unknown_reference_name_returns_error` — parametrized; result is exactly
   `"Error: Reference project 'nope' not found"` and `mock_manager_cls.assert_not_called()`.
4. `test_reference_project_without_url_returns_error` — `github_label_list(reference_name="nourl")`
   returns exactly `"Error: Reference project 'nourl' has no URL configured"`.
5. `test_reference_access_does_not_clone` — patches
   `mcp_workspace.server_reference_tools.ensure_available` and asserts it is never called.
   **This is the test that enforces #255 decision 1; do not drop or weaken it.**

Existing `TestGithubLabelList` in `test_github_write_tools_labels_pr.py:64-161` must stay green
unchanged — it already patches the same target, and the no-reference path still constructs with
`project_dir=`.

## LLM prompt

> Implement step 1 of `pr_info/steps/step_1.md`, using `pr_info/steps/summary.md` for context.
> Work test-first: create `tests/github_operations/test_github_write_tools_reference.py`
> modelled on `tests/github_operations/test_github_read_tools_reference.py` (same
> `reference_projects` fixture shape with non-existent paths, same parametrized `_TOOL_CASES`
> style, same `@patch("mcp_workspace.github_operations.issues.IssueManager")` target), covering
> `github_label_list` only, then add `reference_name: Optional[str] = None` to
> `github_label_list` in `src/mcp_workspace/server.py`, replace
> `IssueManager(project_dir=_project_dir)` with `_issue_manager(reference_name)`, delete the
> now-unused local `IssueManager` import, and update the docstring. Keep the tool synchronous.
> Do not modify any other tool, and do not touch `test_github_read_tools_reference.py` or
> `_github_read_tools_helpers.py`. Use the MCP file tools, then run
> `mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check` (with
> `extra_args: ["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not
> claude_api_integration and not formatter_integration and not github_integration and not
> langchain_integration"]`) and `mcp__mcp-tools-py__run_mypy_check`, and fix everything they
> report. One commit.
