# Step 3 — Export `MergeResult` and `PullRequestData`

**Read first:** `pr_info/steps/summary.md` (Export surface). **Depends on Step 2**
(`MergeResult` must exist). Purely additive public-API change.

## Goal

Add **both** `MergeResult` and `PullRequestData` to the package's public export
surface, so consumers (mcp-coder's shim) can import them from
`mcp_workspace.github_operations`. `PullRequestData` was a prior omission — its
siblings (`CIStatusData`, `LabelData`, `CheckResult`) are already exported.

One commit: test + implementation + checks.

## WHERE

- Implementation: `src/mcp_workspace/github_operations/__init__.py`
  — the `from .pr_manager import ...` line and the `__all__` list.
- Test: add to `tests/github_operations/test_pr_manager.py` (a small importability
  test), or a minimal new `tests/github_operations/test_package_exports.py`.

## WHAT / HOW

- Change the import to bring in the two names alongside the manager:
  `from .pr_manager import MergeResult, PullRequestData, PullRequestManager`
- Add `"MergeResult"` and `"PullRequestData"` to `__all__` (keep it sorted to
  match the existing style).
- Nothing else changes; all other exports stay.

## ALGORITHM

None (declarative export change).

## DATA

`__all__` gains two entries. Both are TypedDicts defined in `pr_manager.py`.

## TESTS

- `test_merge_result_and_pr_data_exported`: 
  `from mcp_workspace.github_operations import MergeResult, PullRequestData`
  succeeds, and both names are present in
  `mcp_workspace.github_operations.__all__`. (No `git_integration` marker needed —
  it is a pure import test.)

## CHECKS

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","-m","not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__tools-py__run_mypy_check`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Implement Step 3
> only (Steps 1–2 already merged). In
> `src/mcp_workspace/github_operations/__init__.py`, import `MergeResult` and
> `PullRequestData` from `.pr_manager` and add both to `__all__` (keep it
> sorted). First add an importability test asserting both names import from
> `mcp_workspace.github_operations` and appear in `__all__` (TDD). Use MCP tools
> only. Run pylint, pytest (fast-unit exclusions), and mypy; fix until all pass.
> This is one commit.
