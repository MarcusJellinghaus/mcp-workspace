# Step 2: `github_issue_view` flag and lookup helper

## LLM prompt

Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_2.md`) for
issue #303. Step 1 (formatter) is already done. Write the tests first, then the
implementation. Run `run_format_code`, pylint, pytest (`extra_args: ["-n", "auto"]`) and
mypy; all must pass. Produce one commit.

## WHERE

- `src/mcp_workspace/server.py` — new helper `_linked_branches` next to `_issue_manager`;
  `github_issue_view` changes.
- `tests/github_operations/test_github_read_tools_issues.py`
- `tests/github_operations/test_github_read_tools_reference.py`

## WHAT

```python
def _linked_branches(number: int, reference_name: Optional[str]) -> Optional[list[str]]:
    """Look up an issue's linked branches; None when the lookup fails for any reason."""

@mcp.tool()
@log_function_call
def github_issue_view(
    number: int,
    include_comments: bool = True,
    max_lines: int = 200,
    reference_name: Optional[str] = None,
    include_linked_branches: bool = False,
) -> str:
```

Document `include_linked_branches` in the tool docstring (it is the MCP tool description):
adds a "Linked branches" line — names, `none`, or `unknown (lookup failed)`; costs two extra
GitHub requests.

## HOW

- Inside `_linked_branches`, lazy-import `IssueBranchManager` from
  `mcp_workspace.github_operations.issues` (same pattern and comment as `_issue_manager`), so
  tests patch `mcp_workspace.github_operations.issues.IssueBranchManager`.
- Use the module-level `logger`, `_project_dir` and `get_reference_repo_url`, all already in
  `server.py`.
- `except Exception:  # pylint: disable=broad-exception-caught` with
  `logger.debug("Linked branch lookup failed", exc_info=True)`, as in
  `checks/branch_status.py::_collect_linked_branch_status`.

## ALGORITHM

`_linked_branches`:
```
try:
    if reference_name is None: manager = IssueBranchManager(project_dir=_project_dir)
    else: manager = IssueBranchManager(repo_url=get_reference_repo_url(reference_name))
    return manager.get_linked_branches_or_none(number)
except Exception: log debug; return None
```

`github_issue_view`, after the not-found return and the comments fetch:
```
linked = _linked_branches(number, reference_name) if include_linked_branches else None
return format_issue_view(issue, comments, max_lines,
                         linked_branches=linked, include_linked_branches=include_linked_branches)
```

## DATA

`_linked_branches` returns `list[str]` (possibly empty) or `None`. The tool still returns a
string; the not-found and outer-error paths are unchanged.

## Tests (write first)

`test_github_read_tools_issues.py` — stack `@patch(".../issues.IssueBranchManager")` with the
existing `@patch(".../issues.IssueManager")`:

- `test_github_issue_view_linked_branches_off` — default call: `IssueBranchManager` not
  called; `"Linked branches" not in result`.
- `test_github_issue_view_linked_branches_on` — lookup returns `["42-fix"]`: result contains
  `Linked branches: 42-fix`; `IssueBranchManager.call_args.kwargs == {"project_dir": project_dir}`
  (use the `project_dir` fixture); `get_linked_branches_or_none` called with `42`.
- `test_github_issue_view_linked_branches_failure` — parametrised over three failures:
  lookup raises, lookup returns `None`, constructor raises `ValueError`. Each: result starts
  with `# #42`, contains `Linked branches: unknown (lookup failed)`, not `Error:`.
- `test_github_issue_view_not_found_skips_linked_branches` — empty issue with flag on: result
  is the unchanged not-found error; `IssueBranchManager` not called.

`test_github_read_tools_reference.py` — separate test, not part of `_TOOL_CASES`:

- `test_issue_view_linked_branches_reference_uses_repo_url` — `reference_projects` fixture,
  `_configure_manager` for `IssueManager`, patched `IssueBranchManager`;
  `github_issue_view(number=42, reference_name="sibling", include_linked_branches=True)`;
  assert `IssueBranchManager.call_args.kwargs == {"repo_url": "https://github.com/owner/sibling"}`.
