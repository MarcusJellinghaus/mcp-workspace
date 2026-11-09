# Step 6 — `github_issue_set_status` MCP tool + `_check_labels` wording

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 6** exactly as described
> in `pr_info/steps/step_6.md`. Step 5 (`issues/status.py`) is already done.
> Write the tests first, then the code. Run pylint, pytest (`-n auto`), mypy and
> vulture via the MCP tools until all pass, format the code, and make exactly
> one commit.

## Precondition

`src/mcp_workspace/github_operations/issues/status.py` defines `set_issue_status`.
If it does not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/server.py`
  - new tool `github_issue_set_status`, placed after `github_issue_edit`
  - delete `_STATUS_LABEL_PREFIX` and its comment (`:88-89`)
  - `_check_labels`: status check via `is_status_label`, error message and comment (`:142-149`)
  - `github_issue_create` / `github_issue_edit` docstrings (`:1389-1391`, `:1467-1469`)
- `vulture_whitelist.py`: add `_.github_issue_set_status`
- `tests/github_operations/test_github_issue_set_status.py` (new)
- `tests/github_operations/test_github_write_tools_reference.py`: add
  `(github_issue_set_status, {"number": 42, "status": "status-01:created"})` to
  `_TOOL_CASES` (`:112-120`) and a matching `"issue_set_status"` entry to
  `_TOOL_IDS` (`:121-129`), and update the assertions that expect the old
  `set-status` advice
- any other test asserting the old `_check_labels` text (search for
  `gh-tool set-status` under `tests/`)

## WHAT

```python
@mcp.tool()
@log_function_call
def github_issue_set_status(
    number: int,
    status: str,
    from_status: str | None = None,
    reference_name: str | None = None,
    refresh_labels: bool = False,
) -> str: ...
```

## HOW

- Body: a lazy import of `set_issue_status`, then
  `try: return set_issue_status(_issue_manager(reference_name), number, status, from_status, refresh_labels)`
  and `except Exception as e: return _tool_error(e)`.
- Docstring:
  - writes to GitHub
  - targets the workspace or a reference project, with no clone needed
  - `status` and `from_status` are full `status-*` label names that already
    exist in the target repo, matched case-insensitively; list them with
    `github_label_list(search="status-")`
  - removes every other `status-*` label
  - `from_status` guard semantics
  - PRs are rejected; closed issues are allowed
  - label cache: 24 h, `refresh_labels`
  - a status change can start workflow automation in the target repo
- `_check_labels` message: `Error: these tools do not modify status-* labels (<offenders>). Use github_issue_set_status`.
  Remove the reference-project "own checkout" clause and its comment.
  `reference_name` stays a parameter, because the unknown-label message still uses it.
- `_check_labels` finds offenders with `is_status_label(n)`, lazily imported
  from `mcp_workspace.github_operations.issues.status` inside the function.
  Delete `_STATUS_LABEL_PREFIX` and its comment (`:88-89`), so the status-label
  rule lives only in `issues/status.py`.
- create/edit docstrings: "… are rejected — use `github_issue_set_status`."

## ALGORITHM

None beyond the delegation above.

## DATA

Returns the string from `set_issue_status`, or the `_tool_error` rendering.

## Tests (write first; mock `mcp_workspace.github_operations.issues.IssueManager`, mocks carry a real `RepoIdentifier`)

- workspace issue: `get_available_labels` returns status labels and
  `get_issue_for_status`/`set_labels` return `IssueData` → the result contains
  old → new and `Labels:`
- reference project `sibling`: the manager is built from the configured URL,
  and `ensure_available` (clone) is not called
- `nourl` reference project → error, as for the other tools
- PR: `get_issue_for_status` raises `ValueError("#5 is a pull request, not an issue")` → `Error: #5 is a pull request…`
- 404 from `get_issue_for_status` → `Error:` containing GitHub's message
- `set_labels` returns empty `IssueData` → unconfirmed text
- after a successful write, the coordinator `<repo>.issues.json` (seeded in
  `cache_dir`) holds the new labels
- `github_issue_create`/`github_issue_edit` with `status-01:created` → error
  naming `github_issue_set_status`, with no write (both workspace and reference)
