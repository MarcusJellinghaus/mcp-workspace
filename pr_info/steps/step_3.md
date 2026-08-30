# Step 3 — `github_issue_create` gains `reference_name`; `_check_labels` learns the name

Read [summary.md](./summary.md) first. Depends on step 2 (`_ref_suffix` exists).

This is the step that changes the two messages `_check_labels` owns. `github_issue_create` is
its first caller to pass a reference name, so the new parameter is exercised the moment it
exists; step 4 wires up the second caller.

## WHERE

- `src/mcp_workspace/server.py` — `_check_labels` (`:71-112`), `github_issue_create` (`:1134-1185`)
- `tests/github_operations/test_github_write_tools_reference.py` — extend

## WHAT

```python
def _check_labels(
    manager: Any,
    add: List[str],
    remove: List[str],
    reference_name: Optional[str] = None,
) -> Optional[str]:


@mcp.tool()
@log_function_call
def github_issue_create(
    title: str,
    body: str = "",
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    reference_name: Optional[str] = None,
) -> str:
```

## HOW

- `_check_labels` keeps `manager: Any` (a real annotation would force a top-level
  `github_operations` import and pull PyGithub onto the startup path — see the existing
  docstring note). Label *validation* needs no work: the manager is already a parameter, so it
  points at the target repository automatically.
- The `status-*` rejection itself is unchanged — only its advice clause. Compose it as
  existing-text-plus-suffix, never as two alternative sentences.
- Unknown-label message (`:111`) takes `_ref_suffix(reference_name)` **before the colon**, not
  at the end: appended, `"unknown label(s): a, b in reference project 'x'"` reads as though the
  suffix were part of the label list. Placed before the colon the list stays terminal and
  unambiguous for one label or many, and the `None` path is still byte-identical because the
  suffix is empty.
- Add `reference_name` to `_check_labels`'s docstring `Args:` (the repo's docstring lint
  requires it; keep the existing `# noqa: DOC502` on the closing quotes).
- `github_issue_create`: delete the local `IssueManager` import (`:1159-1160`, comment
  included), swap `:1163` to `_issue_manager(reference_name)`, pass `reference_name` to
  `_check_labels` at `:1164`, and append `_ref_suffix(reference_name)` to the creation-failure
  sentinel at `:1176`.
- Docstrings: relax `:1142` ("in this repository" → the workspace repository or a reference
  project), reword `:1144-1147` so the `set-status` advice is not stated unconditionally and
  labels are validated against "the target repository", relax the `labels:` entry
  ("must already exist in the target repository"), and add:

  ```
  reference_name: Optional reference project name. When set, the issue is
      created in that project's GitHub repository instead of the workspace
      repository.
  ```

- Tool stays `def`. `_login_cache` stays a single slot keyed on `"login"` — the authenticated
  user is a property of the token, not the target repo.

## ALGORITHM

```
_check_labels(manager, add, remove, reference_name):
    offenders = [n for n in add+remove if n.casefold().startswith("status-")]
    if offenders:
        advice = "Use: mcp-coder gh-tool set-status <label>"
        if reference_name is not None:
            advice += f" from the '{reference_name}' project's own checkout"
        return f"Error: these tools do not modify status-* labels ({...}). {advice}"
    if not add: return None
    known = {label["name"].casefold() for label in manager.get_available_labels()}
    unknown = [n for n in add if n.casefold() not in known]
    if unknown: return f"Error: unknown label(s){_ref_suffix(reference_name)}: {', '.join(unknown)}"
    return None
```

`github_issue_create` is otherwise untouched: build manager → `_check_labels` →
`_resolve_assignees` → `create_issue` → sentinel check → three-line success block.

## DATA

Messages, workspace path (`reference_name=None`) — **byte-identical to today**:

- `"Error: these tools do not modify status-* labels (status-01:created). Use: mcp-coder gh-tool set-status <label>"`
- `"Error: unknown label(s): bugg"`
- `"Error: unknown label(s): bugg, bugz"` (multi-label, unchanged)
- `"Error: issue creation failed - no issue was created"`

Cross-repo (`reference_name="sibling"`):

- `"… set-status <label> from the 'sibling' project's own checkout"`
- `"Error: unknown label(s) in reference project 'sibling': bugg"`
- `"Error: unknown label(s) in reference project 'sibling': bugg, bugz"` — the label list stays
  terminal, so the reference project cannot be misread as a third label
- `"Error: issue creation failed - no issue was created in reference project 'sibling'"`

Success output is unchanged and needs no suffix — it returns a URL.

## Tests (write first)

In `test_github_write_tools_reference.py`:

1. Add `(github_issue_create, {"title": "T"})` to `_TOOL_CASES` / `"issue_create"` to `_TOOL_IDS`.
2. Extend `_make_manager()` with `create_issue` returning a real `IssueData` (number 42),
   `get_available_labels` returning `[{"name": "bug", ...}]`, and
   `_github_client.get_user.return_value.login`.
3. `test_status_guard_points_at_reference_checkout` — `github_issue_create(title="T",
   labels=["status-01:created"], reference_name="sibling")` mentions `"sibling"` and
   `"own checkout"`, and `create_issue` / `get_available_labels` are not called.
4. `test_unknown_label_names_reference_project` — parametrized over one and two unknown labels;
   results are exactly `"Error: unknown label(s) in reference project 'sibling': bugg"` and
   `"Error: unknown label(s) in reference project 'sibling': bugg, bugz"`, so the multi-label
   case proves the suffix is not readable as another label.
5. `test_create_failure_names_reference_project` — `create_issue` returns
   `create_empty_issue_data()`; result ends with `" in reference project 'sibling'"`.

**Regression guard:** `test_github_write_tools_issues.py:233` asserts
`result == "Error: unknown label(s): bug"` by exact equality, and `:154`/`:264` assert
`"set-status" in result`. All three call without `reference_name` and must stay green
**without being edited** — if they need editing, the suffix approach was not followed.

## LLM prompt

> Implement step 3 of `pr_info/steps/step_3.md`, using `pr_info/steps/summary.md` for context.
> Work test-first: extend `tests/github_operations/test_github_write_tools_reference.py` with
> the `github_issue_create` case and the three message tests described in the step, then add
> `reference_name: Optional[str] = None` to `_check_labels` and to `github_issue_create` in
> `src/mcp_workspace/server.py`, make the `status-*` advice conditional by *appending* a clause
> and the unknown-label message conditional by inserting `_ref_suffix(reference_name)` before
> its colon so the label list stays terminal (never by rewriting either message), swap the manager
> construction to `_issue_manager(reference_name)`, pass `reference_name` into `_check_labels`,
> append `_ref_suffix(reference_name)` to the creation-failure sentinel, delete the now-unused
> local `IssueManager` import, and update the docstrings. The workspace path
> (`reference_name=None`) must produce byte-identical output to today — in particular
> `tests/github_operations/test_github_write_tools_issues.py` must pass unmodified. Do not
> modify `github_issue_edit` in this step. Use the MCP file tools, then run
> `mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check` (with
> `extra_args: ["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not
> claude_api_integration and not formatter_integration and not github_integration and not
> langchain_integration"]`) and `mcp__mcp-tools-py__run_mypy_check`, and fix everything they
> report. One commit.
