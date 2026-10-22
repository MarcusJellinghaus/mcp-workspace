# Step 1 — Ref-name check for `### Base Branch`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md`.
> TDD: write the tests listed below first, see them fail, then implement.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy until all pass, then
> `run_format_code` and make one commit.

## WHERE

- `src/mcp_workspace/github_operations/issues/base.py`
- `src/mcp_workspace/server.py` — `_check_base_branch` docstring only
- `src/mcp_workspace/checks/branch_status.py` — `_malformed_first_line` docstring only
- `README.md` — line ~80 (`--enforce-base-branch-format`)
- Tests: `tests/github_operations/issues/test_base.py`,
  `tests/test_server_enforce_base_branch_format.py`,
  `tests/github_operations/test_github_write_tools_issues.py`,
  `tests/github_operations/test_github_write_tools_issue_edit_base_branch.py`,
  `tests/checks/test_branch_status_base_branch.py`

## WHAT

```python
class InvalidBaseBranchRefError(MalformedBaseBranchError):
    """Raised when the Base Branch value is a single line but not a valid git ref name."""
    def __init__(self, content: str) -> None: ...

def is_valid_ref_name(name: str) -> bool: ...
```

- Export both in `__all__`.
- `parse_base_branch`: once the multi-line check passes, raise
  `InvalidBaseBranchRefError(content)` if `not is_valid_ref_name(content)`. Update the
  `Raises:` section of its docstring.
- `format_malformed_base_branch(error)`: same signature. For
  `InvalidBaseBranchRefError` return e.g.
  ``"`### Base Branch` must be a valid git branch name; {content!r} is not (no spaces, '..', control characters or ~^:?*[\\). Fix the name or remove the section."``
  Otherwise return today's sentence, unchanged.

## HOW

- `InvalidBaseBranchRefError.__init__`: call `super().__init__(content)`, then set
  `self.args = (f"Base branch is not a valid git ref name: {content!r}",)`, so
  `.content` and `isinstance(..., MalformedBaseBranchError)` both keep working.
- No change is needed in `_check_base_branch` (server.py ~157), `IssueManager` or
  `_malformed_first_line` (branch_status.py ~192). They catch `MalformedBaseBranchError`,
  and for the new error `exc.content.splitlines()[0]` is the value itself. Update only
  their docstrings ("multi-line" → "multi-line or invalid ref name").
- `validate_branch_name` (`branch_queries.py`) stays unchanged.

## ALGORITHM

```
_INVALID_REF_CHARS = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]|\.\.|@\{|//")
def is_valid_ref_name(name):
    if not name or _INVALID_REF_CHARS.search(name): return False
    if name.startswith(("-", ".")): return False
    if name.endswith((".", "/", ".lock")): return False
    return True
```

## DATA

- `parse_base_branch` returns `str | None` as before. It raises
  `MalformedBaseBranchError` for multi-line content (unchanged) and
  `InvalidBaseBranchRefError` for an invalid single-line ref.

## Tests (write first)

- `is_valid_ref_name`:
  - true for `main`, `feature/v2`, `release-1.2`, `x`;
  - false for `main branch`, `a..b`, `a~1`, `a^`, `a:b`, `a?`, `a*`, `a[b`, `a\b`, `-x`,
    `.x`, `x.`, `x/`, `x.lock`, `a@{b`, `a//b`, `a\tb`, `a\x7fb`.
- `parse_base_branch("### Base Branch\n\nmain branch\n")` raises
  `InvalidBaseBranchRefError`, which is also a `MalformedBaseBranchError`; `.content`
  is `"main branch"`.
- `format_malformed_base_branch` names the ref problem, includes `'main branch'`, and
  does not say "on one line". The multi-line message is unchanged.
- `_check_base_branch("### Base Branch\n\nmain branch\n")` returns `"Error: ..."`.
  It returns None when enforcement is disabled.
- `github_issue_create` and `github_issue_edit` (with a body) reject an invalid ref and
  issue no write. `github_issue_edit` without a body is not checked.
- `check_branch_status` with a trusted issue whose `base_branch_error` comes from
  `main branch`: the MALFORMED line shows `'main branch'`, not `''`. Build the report
  from a body; don't hard-code the sentence.
- Run the full suite. If an existing test uses an invalid ref as a "valid" base branch
  value, change it to a valid one.
