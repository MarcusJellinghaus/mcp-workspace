# Step 4 — `github_issue_edit` gains `reference_name`

Read [summary.md](./summary.md) first. Depends on step 3 (`_check_labels` accepts the name).

The last of the four tools, and the one with the highest stakes: a wrong-but-valid
`reference_name` together with `state="closed"` can close an issue in the wrong sibling repo.
Recoverable, and still narrower than the `gh --repo` route it replaces, but it is why the
docstring must be explicit about what `reference_name` retargets.

## WHERE

- `src/mcp_workspace/server.py` — `github_issue_edit` (`:1188-1323`)
- `tests/github_operations/test_github_write_tools_reference.py` — extend

## WHAT

```python
@mcp.tool()
@log_function_call
def github_issue_edit(
    number: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
    add_assignees: Optional[List[str]] = None,
    state: Optional[str] = None,
    reference_name: Optional[str] = None,
) -> str:
```

## HOW

- The local import block at `:1226-1229` loses **only** `IssueManager`; `GithubException`
  (`:1227`) and `create_empty_issue_data` (`:1229`) are still used by the partial-failure path
  and must stay. Adjust the block comment if it no longer describes plural imports correctly.
- Swap `:1242` to `manager = _issue_manager(reference_name)`, and pass `reference_name` as the
  fourth argument to `_check_labels` at `:1243`.
- The pre-write validations at `:1235-1240` (number, title, state) run **before** the manager is
  built and stay exactly where they are — an invalid argument must not depend on resolving a
  reference project.
- One message in this tool does need `_ref_suffix(reference_name)`: the nothing-was-written
  sentinel at `:1285-1288`,
  `"Error: issue #<n> not found or not accessible (<reason>) - no changes were made"`. It names
  no repository and returns no URL, and it is the most likely cross-repo failure of all — a
  wrong-but-valid `reference_name` pointing at a repository that has no issue with that number.
  Insert the suffix directly after `"not accessible"`, before the `(<reason>)` clause, so the
  reason and the `- no changes were made` tail stay adjacent and the `None` path is
  byte-identical.
- Nothing else in the tool changes: `edit_issue`, the `attempted` write log, the re-read through
  the same `manager`, `_edit_change_lines`, and the result block are all manager-driven and
  therefore already follow the target repository. The remaining messages need no suffix: the
  partial-failure variants name the issue number and the attempted writes, and every path that
  reaches the result block prints the issue URL, which identifies the repository.
- Docstrings: relax `:1199` ("in this repository"), reword `:1202-1204` so the `set-status`
  advice is not stated unconditionally (it mirrors the guard's now-conditional runtime text),
  relax the `add_labels:` entry ("must already exist in the target repository"), and add:

  ```
  reference_name: Optional reference project name. When set, the issue is
      edited in that project's GitHub repository instead of the workspace
      repository.
  ```

- Tool stays `def`.

## ALGORITHM

```
github_issue_edit(..., reference_name):
    validate number / title / state            # unchanged, before any resolution
    manager = _issue_manager(reference_name)
    err = _check_labels(manager, add_labels or [], remove_labels or [], reference_name)
    if err: return err
    ... resolve assignees, edit_issue, re-read on failure ...
    if re-read empty and nothing attempted:
        return (f"Error: issue #{number} not found or not accessible"
                f"{_ref_suffix(reference_name)} ({reason}){reread_error}"
                " - no changes were made")
    ... rest unchanged (partial-failure variants, render) ...
```

## DATA

Return values unchanged in shape:
`"Updated issue #<n> — <url> (state: <state>)"` plus `Labels:` / `Assignees:` lines, or the
warning/error-prefixed variants. Cross-repo the URL identifies the repository, so every message
that reaches the result block stays as it is.

The one message in this tool that differs cross-repo is the nothing-was-written sentinel, which
returns no URL:

- workspace (`reference_name=None`) — **byte-identical to today**:
  `"Error: issue #42 not found or not accessible (swallowed API error) - no changes were made"`
- cross-repo (`reference_name="sibling"`):
  `"Error: issue #42 not found or not accessible in reference project 'sibling' (swallowed API error) - no changes were made"`

The `status-*` guard message also differs cross-repo, but it comes from `_check_labels`
(step 3), not from this tool.

## Tests (write first)

In `test_github_write_tools_reference.py`:

1. Add `(github_issue_edit, {"number": 42, "title": "T"})` to `_TOOL_CASES` /
   `"issue_edit"` to `_TOOL_IDS` — the parametrized repo_url / project_dir / unknown-name tests
   then cover all four tools, completing the table.
2. Extend `_make_manager()` with `edit_issue` and `get_issue` returning a real `IssueData`.
3. `test_edit_status_guard_points_at_reference_checkout` —
   `github_issue_edit(number=42, add_labels=["status-04:in-progress"], reference_name="sibling")`
   mentions `"sibling"` and `"own checkout"`, and `edit_issue` is not called.
4. `test_edit_invalid_number_does_not_resolve_reference` —
   `github_issue_edit(number=0, reference_name="nope")` returns the invalid-number error, not
   the unknown-reference error, proving validation still precedes resolution.
5. `test_edit_not_found_names_reference_project` — `edit_issue` and the re-read `get_issue` both
   return `create_empty_issue_data()` and no write is logged in `attempted`; assert the result is
   exactly `"Error: issue #42 not found or not accessible in reference project 'sibling' "`
   `"(swallowed API error) - no changes were made"`.
6. `test_edit_not_found_without_reference_is_unchanged` — same setup, no `reference_name`; assert
   exactly `"Error: issue #42 not found or not accessible (swallowed API error) - no changes were made"`.

**Regression guard:** `test_github_write_tools_issue_edit.py:503`, `:519` and `:534` assert
`"set-status" in result` on the workspace path and must stay green **without being edited**.

## LLM prompt

> Implement step 4 of `pr_info/steps/step_4.md`, using `pr_info/steps/summary.md` for context.
> Work test-first: extend `tests/github_operations/test_github_write_tools_reference.py` with
> the `github_issue_edit` case and the four tests described in the step, then add
> `reference_name: Optional[str] = None` as the last parameter of `github_issue_edit` in
> `src/mcp_workspace/server.py`, swap its manager construction to `_issue_manager(reference_name)`,
> pass `reference_name` into `_check_labels`, insert `_ref_suffix(reference_name)` after
> `"not found or not accessible"` in the nothing-was-written sentinel, remove **only**
> `IssueManager` from the local import block (keep `GithubException` and
> `create_empty_issue_data`), and update the docstring.
> Leave the pre-write validations of number/title/state ahead of the manager construction. The
> workspace path must produce byte-identical output to today, and
> `tests/github_operations/test_github_write_tools_issue_edit.py` must pass unmodified. Use the
> MCP file tools, then run `mcp__mcp-tools-py__run_pylint_check`,
> `mcp__mcp-tools-py__run_pytest_check` (with `extra_args: ["-n", "auto", "-m", "not
> git_integration and not claude_cli_integration and not claude_api_integration and not
> formatter_integration and not github_integration and not langchain_integration"]`) and
> `mcp__mcp-tools-py__run_mypy_check`, and fix everything they report. One commit.
