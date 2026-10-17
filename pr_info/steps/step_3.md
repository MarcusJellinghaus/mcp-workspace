# Step 3 — `_check_base_branch` helper in `server.py`

See `pr_info/steps/summary.md` for full context. This step adds the shared
validation helper and tests it directly. It is not yet called from
`github_issue_create` or `github_issue_edit` (steps 4 and 5).

## Precondition

`src/mcp_workspace/server.py` must contain `_check_labels` as described in the
summary, and `_enforce_base_branch_format` / `set_enforce_base_branch_format`
from step 2 must already exist. `src/mcp_workspace/github_operations/issues/base.py`
must expose `MalformedBaseBranchError` and `parse_base_branch` (step 1). If any
is missing, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/server.py` (modify — add helper only)
- `tests/test_server_enforce_base_branch_format.py` (modify — add helper tests)

## WHAT

```python
def _check_base_branch(body: Optional[str]) -> Optional[str]:
    """Reject a multi-line ### Base Branch section before any write.

    Args:
        body: Candidate issue body, or None when the caller is not changing
            the body (as in github_issue_edit).

    Returns:
        An error string naming the problem, the fix, and the section's first
        line, or None when the section is absent, empty, a single valid
        line, or the check is disabled.
    """
```

Place it directly below `_check_labels` (after its closing blank line), before
`_resolve_assignees`.

## HOW

- Lazy import inside the function body, matching the pattern already used
  elsewhere in `server.py` for `github_operations` imports:
  ```python
  from mcp_workspace.github_operations.issues.base import (
      MalformedBaseBranchError,
      parse_base_branch,
  )
  ```
- Reads the module global `_enforce_base_branch_format` directly (no
  parameter) — same style as `_fail_on_reviews` being read directly inside
  `check_branch_status`.
- No caller wiring in this step.

## ALGORITHM

```
_check_base_branch(body):
    if not _enforce_base_branch_format:
        return None
    import parse_base_branch, MalformedBaseBranchError   # lazy
    try:
        parse_base_branch(body or "")
    except MalformedBaseBranchError as exc:
        first_line = exc.content.splitlines()[0]
        return (
            "Error: `### Base Branch` must contain only the branch name on "
            "one line; move other text to another section. First line: "
            f"{first_line!r}"
        )
    return None
```

`body or ""` is what makes the helper safe to call with `body=None` (the
`github_issue_edit` case where the caller did not pass a body): `parse_base_branch`
already treats falsy input as "not specified" and returns `None` without
raising, so no `if body is not None:` guard is needed at any call site.

## DATA

- Return value: `Optional[str]`. `None` means "no error, proceed". A non-`None`
  string is the full "Error: ..." text, ready to return directly from a tool.
- The error text is fixed except for the appended first line; keep the exact
  wording above so step 4/5 tests can assert on it verbatim.

## TDD order

Add to `tests/test_server_enforce_base_branch_format.py`, a new
`TestCheckBaseBranch` class (same file as step 2's flag tests; import
`_check_base_branch` from `mcp_workspace.server`), with a fixture resetting
`server_module._enforce_base_branch_format = True` after each test:

1. `test_absent_section_is_none`: `_check_base_branch("### Description\n\nx")`
   → `None`.
2. `test_no_body_is_none`: `_check_base_branch(None)` → `None`.
3. `test_empty_section_is_none`:
   `_check_base_branch("### Base Branch\n\n### Next")` → `None`.
4. `test_valid_single_line_is_none`:
   `_check_base_branch("### Base Branch\n\nfeature/v2\n\n### Description")` →
   `None`.
5. `test_malformed_returns_error_with_first_line`:
   `_check_base_branch("### Base Branch\n\nline1\nline2\n")` → a string that
   contains `"### Base Branch"`, `"one line"`, and `"line1"` (the first line),
   and does not contain `"line2"`.
6. `test_crlf_malformed_is_rejected`:
   `_check_base_branch("### Base Branch\r\n\r\nline1\r\nline2\r\n")` → error
   string whose embedded first line is exactly `"line1"` (no trailing `\r`).
7. `test_crlf_valid_is_accepted`:
   `_check_base_branch("### Base Branch\r\n\r\nfeature/v2\r\n")` → `None`.
8. `test_flag_off_always_none`: set
   `server_module._enforce_base_branch_format = False`; call with the
   malformed body from case 5 → `None`.

Run these first — they fail (function does not exist). Implement the helper.
Re-run — all pass, plus the full `tests/test_server_enforce_base_branch_format.py`
file from step 2 stays green. Also re-run
`tests/test_startup_performance.py::test_server_import_does_not_eagerly_load_github_or_gitpython`
specifically — it must still pass, confirming the lazy import did not move to
module level.

## Checks and commit

Run `mcp__mcp-tools-py__run_format_code`, then
`mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check`
(`extra_args: ["-n", "auto"]`), `mcp__mcp-tools-py__run_mypy_check`. All must
pass. Then one commit:

```
feat(server): add _check_base_branch helper (unused)

Shared helper next to _check_labels for github_issue_create and
github_issue_edit to validate a Base Branch section before any write.
Lazily imports parse_base_branch/MalformedBaseBranchError to keep
PyGithub off the server startup path. Not yet called by either tool.
```

## LLM prompt for this step

```
Read pr_info/steps/summary.md for context, then implement
pr_info/steps/step_3.md exactly as written. Follow TDD: add the
TestCheckBaseBranch tests to tests/test_server_enforce_base_branch_format.py
first, confirm they fail, then add _check_base_branch to
src/mcp_workspace/server.py directly below _check_labels, using a lazy import
inside the function body. Do not call this helper from github_issue_create or
github_issue_edit in this step. Run format, pylint, pytest (-n auto), and
mypy, including tests/test_startup_performance.py; all must pass. If the
precondition in step_3.md does not hold, write one line to
pr_info/.blocked.txt and stop. Make exactly one commit.
```
