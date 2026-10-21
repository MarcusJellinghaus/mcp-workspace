# Step 2 — Shared message helper

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_2.md`). Implement
> step 2 only: tests first, then add `format_malformed_base_branch` to `issues/base.py` and
> switch `server._check_base_branch` to it. Run pylint, pytest (`-n auto`) and mypy until
> green, run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/github_operations/issues/base.py`
- `src/mcp_workspace/server.py` — `_check_base_branch`
- `tests/github_operations/issues/test_base.py`
- `tests/test_server_enforce_base_branch_format.py`
- `tests/github_operations/test_github_write_tools_issue_edit_base_branch.py`

## WHAT

```python
def format_malformed_base_branch(error: MalformedBaseBranchError) -> str:
    """Return the ready-to-show sentence for a malformed Base Branch section (no prefix)."""
```

Add `"format_malformed_base_branch"` to `base.__all__`.

## HOW

`_check_base_branch` keeps its lazy import, now also importing the helper:

```python
except MalformedBaseBranchError as exc:
    return f"Error: {format_malformed_base_branch(exc)}"
```

## ALGORITHM

```
first_line = error.content.splitlines()[0]
return ("`### Base Branch` must contain only the branch name on one line; "
        f"move other text to another section. First line: {first_line!r}")
```

## DATA

Bare sentence, e.g.
`` `### Base Branch` must contain only the branch name on one line; move other text to another section. First line: 'epic/multi-language' ``.
`_check_base_branch` output is byte-identical to today.

## Tests (write first)

- `test_base.py`: helper returns the exact sentence above for
  `MalformedBaseBranchError("epic/multi-language\nmore")`; no `Error:` prefix.
- Existing `TestCheckBaseBranch` stays green unchanged (same text).
- `test_server_enforce_base_branch_format.py`: body that quotes `### Base Branch` + two lines
  only inside a ```` ``` ```` fence → `_check_base_branch` returns `None`.
- Write-tool tests: `github_issue_create` and `github_issue_edit` accept such a body (follow
  the existing patterns in `test_github_write_tools_issue_edit_base_branch.py`; create test in
  the same file or the existing create-tool base-branch tests).
