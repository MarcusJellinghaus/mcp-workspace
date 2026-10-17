# Step 5 — wire `_check_base_branch` into `github_issue_edit`

See `pr_info/steps/summary.md` for full context.

## Precondition

`src/mcp_workspace/server.py` must contain `_check_base_branch` (step 3) and
`github_issue_edit`'s pre-write validation block exactly as described (the
`number <= 0` / `title.strip()` / `state` checks, followed by
`manager = _issue_manager(reference_name)`). If not, write one line to
`pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/server.py` (modify — `github_issue_edit` only)
- `tests/github_operations/test_github_write_tools_issue_edit.py` (modify — add tests)

## WHAT

No new function signatures. `github_issue_edit(number, title=None, body=None,
add_labels=None, remove_labels=None, add_assignees=None, state=None,
reference_name=None) -> str` keeps its signature; only its body and docstring
change.

## HOW

Add one call in the existing pre-write validation block, after the `state`
check and before `manager = _issue_manager(reference_name)`:

```python
if number <= 0:
    return f"Error: invalid issue number: {number}"
if title is not None and not title.strip():
    return "Error: Issue title cannot be empty"
if state not in (None, "open", "closed"):
    return f"Error: state must be 'open' or 'closed', got: {state}"
body_error = _check_base_branch(body)
if body_error:
    return body_error

manager = _issue_manager(reference_name)
```

`body` is `Optional[str]` here and is passed straight through — no
`if body is not None:` wrapper. `_check_base_branch` already returns `None`
for `body=None` (step 3's `body or ""`), so an edit call that does not touch
`body` (labels/assignees/state/title only) is never blocked, with no special
case to maintain.

Docstring: add the same one-sentence note as in step 4's `github_issue_create`
docstring, adapted to "when `body` is passed".

## ALGORITHM

```
github_issue_edit(number, title, body, ..., state, reference_name):
    if number <= 0: return error
    if title is not None and not title.strip(): return error
    if state not in (None, "open", "closed"): return error
    body_error = _check_base_branch(body)
    if body_error: return body_error
    manager = _issue_manager(reference_name)
    ... unchanged from here ...
```

## DATA

- No change to the documented return shapes, except a malformed `body`
  returns the `_check_base_branch` error string instead of attempting the edit.

## TDD order

Add to `tests/github_operations/test_github_write_tools_issue_edit.py`:

1. `test_github_issue_edit_rejects_malformed_base_branch`: patch
   `mcp_workspace.github_operations.issues.IssueManager` (same pattern as the
   create-tool tests); call
   `github_issue_edit(number=42, body="### Base Branch\n\nline1\nline2\n")`;
   assert `result.startswith("Error:")`, `"line1" in result`, and
   `mock_manager_cls.assert_not_called()` (proving the check runs before
   `_issue_manager(...)`).
2. `test_github_issue_edit_accepts_valid_base_branch`: body with a single-line
   section; manager returns `_make_issue()`; assert result starts with
   "Updated issue".
3. `test_github_issue_edit_accepts_body_without_base_branch_section`: body
   with no `### Base Branch` heading at all; assert result starts with
   "Updated issue".
4. `test_github_issue_edit_accepts_empty_base_branch_section`: body with
   `### Base Branch\n\n### Next`; assert result starts with "Updated issue".
5. `test_github_issue_edit_without_body_is_never_blocked`: call
   `github_issue_edit(number=42, add_labels=["bug"])` (no `body` kwarg at
   all) with a malformed-looking state otherwise irrelevant; assert the
   result does NOT start with the `_check_base_branch` error text and that
   `manager.edit_issue` was called — i.e. the omitted-body path reaches the
   manager exactly as before this feature existed.
6. `test_github_issue_edit_rejects_malformed_base_branch_crlf`: body
   `"### Base Branch\r\n\r\nline1\r\nline2\r\n"`; assert rejected with
   `"line1"` and no trailing `\r` in the embedded first line.
7. `test_github_issue_edit_with_flag_off_writes_malformed_base_branch`:
   `with patch("mcp_workspace.server._enforce_base_branch_format", False):`
   call with the malformed body from case 1; assert result starts with
   "Updated issue".

Run these first — they fail (not wired yet). Wire the check in. Re-run — all
pass, and the full existing `github_issue_edit` test file stays green
(partial-failure paths, label/assignee handling, happy path).

## Checks and commit

Run `mcp__mcp-tools-py__run_format_code`, then
`mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check`
(`extra_args: ["-n", "auto"]`), `mcp__mcp-tools-py__run_mypy_check`. All must
pass. Then one commit:

```
feat(server): reject malformed Base Branch in github_issue_edit

github_issue_edit now runs _check_base_branch(body) in its pre-write
validation block, before constructing an IssueManager. An edit call that
does not pass body is never affected. Disable via
--no-enforce-base-branch-format.
```

## LLM prompt for this step

```
Read pr_info/steps/summary.md for context, then implement
pr_info/steps/step_5.md exactly as written. Follow TDD: add the new tests to
tests/github_operations/test_github_write_tools_issue_edit.py first, confirm
they fail, then add the _check_base_branch(body) call to github_issue_edit's
existing pre-write validation block in src/mcp_workspace/server.py, directly
before `manager = _issue_manager(reference_name)`, and update the tool's
docstring. Do not add an `if body is not None` wrapper around the call — the
helper already handles body=None. Run format, pylint, pytest (-n auto), and
mypy; all must pass, including the full existing test file for this tool. If
the precondition in step_5.md does not hold, write one line to
pr_info/.blocked.txt and stop. Make exactly one commit.
```
