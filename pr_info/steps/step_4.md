# Step 4 — wire `_check_base_branch` into `github_issue_create`

See `pr_info/steps/summary.md` for full context.

## Precondition

`src/mcp_workspace/server.py` must contain `_check_base_branch` (step 3) and
`github_issue_create` exactly as described (its `try:` block starting with
`manager = _issue_manager(reference_name)`, followed by `_check_labels`). If
not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/server.py` (modify — `github_issue_create` only)
- `tests/github_operations/test_github_write_tools_issues.py` (modify — add tests)

## WHAT

No new function signatures. `github_issue_create(title, body="", labels=None,
assignees=None, reference_name=None) -> str` keeps its signature; only its body
and docstring change.

## HOW

Insert the check as the first statement inside the existing `try:` block, so
it runs before `manager = _issue_manager(reference_name)`:

```python
try:
    body_error = _check_base_branch(body)
    if body_error:
        return body_error
    manager = _issue_manager(reference_name)
    label_error = _check_labels(manager, labels or [], [], reference_name)
    ...
```

Docstring: add one sentence after the existing "Workflow status labels ..."
paragraph, e.g. "A malformed `### Base Branch` section (more than one line)
is rejected before any write, unless the server was started with
`--no-enforce-base-branch-format`."

## ALGORITHM

```
github_issue_create(title, body, labels, assignees, reference_name):
    body_error = _check_base_branch(body)
    if body_error: return body_error
    manager = _issue_manager(reference_name)
    ... unchanged from here ...
```

## DATA

- No change to the success/failure return shapes already documented on the
  tool, except that a malformed body now returns the `_check_base_branch`
  error string instead of "Created issue #...".

## TDD order

Add to `tests/github_operations/test_github_write_tools_issues.py`, near the
label-rejection tests (`test_github_issue_create_rejects_status_label` etc.),
reusing the existing `@patch("mcp_workspace.github_operations.issues.IssueManager")`
pattern:

1. `test_github_issue_create_rejects_malformed_base_branch`:
   ```python
   result = github_issue_create(
       title="Test issue",
       body="### Base Branch\n\nline1\nline2\n",
   )
   assert result.startswith("Error:")
   assert "line1" in result
   mock_manager_cls.assert_not_called()
   ```
   (`mock_manager_cls.assert_not_called()` is the proof the check runs before
   `_issue_manager(...)` — no manager was even constructed.)
2. `test_github_issue_create_accepts_valid_base_branch`: body with a single-line
   section; `_make_manager()`; assert the result starts with "Created issue".
3. `test_github_issue_create_accepts_body_without_base_branch_section`: body
   with no `### Base Branch` heading at all; assert "Created issue".
4. `test_github_issue_create_accepts_empty_base_branch_section`: body with
   `### Base Branch\n\n### Next`; assert "Created issue".
5. `test_github_issue_create_rejects_malformed_base_branch_crlf`: body
   `"### Base Branch\r\n\r\nline1\r\nline2\r\n"`; assert `result.startswith("Error:")`
   and `"line1"` in result (no trailing `\r` in the embedded first line, i.e.
   `"line1\r"` is NOT in result).
6. `test_github_issue_create_accepts_valid_base_branch_crlf`: body
   `"### Base Branch\r\n\r\nfeature/v2\r\n"`; assert "Created issue".
7. `test_github_issue_create_with_flag_off_writes_malformed_base_branch`:
   `with patch("mcp_workspace.server._enforce_base_branch_format", False):`
   call with the malformed body from case 1; assert the result starts with
   "Created issue" (old, pre-#320 behavior preserved).

Run these first — they fail (not wired yet, or — for the flag-off case — the
module attribute to patch doesn't exist until step 2/3, which are already
merged by this point). Wire the check into `github_issue_create`. Re-run —
all pass, and the full existing `github_issue_create` test suite in that file
stays green (labels, assignees, happy path, exception handling).

## Checks and commit

Run `mcp__mcp-tools-py__run_format_code`, then
`mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check`
(`extra_args: ["-n", "auto"]`), `mcp__mcp-tools-py__run_mypy_check`. All must
pass. Then one commit:

```
feat(server): reject malformed Base Branch in github_issue_create

github_issue_create now runs _check_base_branch(body) before constructing
an IssueManager, so a multi-line ### Base Branch section is refused with
no network call instead of silently losing the base branch. Disable via
--no-enforce-base-branch-format.
```

## LLM prompt for this step

```
Read pr_info/steps/summary.md for context, then implement
pr_info/steps/step_4.md exactly as written. Follow TDD: add the new tests to
tests/github_operations/test_github_write_tools_issues.py first, confirm they
fail, then wire _check_base_branch(body) into github_issue_create in
src/mcp_workspace/server.py as the first statement in its try block, and
update the tool's docstring. Do not modify github_issue_edit in this step.
Run format, pylint, pytest (-n auto), and mypy; all must pass, including the
full existing test file for this tool. If the precondition in step_4.md does
not hold, write one line to pr_info/.blocked.txt and stop. Make exactly one
commit.
```
