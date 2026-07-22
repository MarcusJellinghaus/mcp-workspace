# Step 4 — Create `test_manager.py` (rename core + fold `test_list_issues.py`)

> Read `pr_info/steps/summary.md` first. This is Step 4 of 6. One commit.
> Must run **after** Step 3 (the core file has already lost its `validate_*` tests).

## Kind
Rename + fold. The `manager.py` mirror is the (already-trimmed) core file plus the
function-focused `test_list_issues.py`. Combined ≈ 620 lines → **stays a single file**.

## WHERE
- Rename: `tests/github_operations/test_issue_manager_core.py`
  → `tests/github_operations/issues/test_manager.py`
- Fold in then delete: `tests/github_operations/issues/test_list_issues.py`
  (class `TestListIssuesExtendedParams`)

## WHAT
Produce one `test_manager.py` containing the core `IssueManager` CRUD/list tests
(`TestIssueManagerCore`, minus the extracted `validate_*`) **and**
`TestListIssuesExtendedParams`.

## HOW
1. `move_file("tests/github_operations/test_issue_manager_core.py",
   "tests/github_operations/issues/test_manager.py")` (git-mv the trimmed core).
2. Append `TestListIssuesExtendedParams` (verbatim, with its imports) into
   `test_manager.py`; merge duplicate imports.
3. `delete_this_file("tests/github_operations/issues/test_list_issues.py")`.

Fixtures (`mock_issue_manager`, etc.) still cascade from the parent conftest — no changes.
Preserve the class-level `@pytest.mark.git_integration` markers as-is.

## ALGORITHM
```
move core -> issues/test_manager.py
open test_list_issues.py; copy its class + any imports it needs
append class into test_manager.py; dedupe the import block
delete test_list_issues.py
pytest tests/github_operations/issues/test_manager.py (incl. git markers) -> all pass
```

## DATA
No new data structures. Deliverable = one merged `test_manager.py`; `test_list_issues.py`
gone.

## Verify (MCP tools only)
- `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","tests/github_operations/issues/test_manager.py"])`
  (keep git markers) — merged tests pass.
- `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","--collect-only"])` — no dangling
  references to the old paths; no duplicate test basenames.
- `mcp__mcp-workspace__check_file_size(max_lines=750)` — `test_manager.py` under 750.
- `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_mypy_check`.

## Done when
`test_manager.py` exists (core + folded list-issues), `test_issue_manager_core.py` and
`test_list_issues.py` gone, under 750, all pass, checks green. One commit.

## LLM prompt
> Implement Step 4 from `pr_info/steps/step_4.md` (context in `pr_info/steps/summary.md`).
> `move_file` `tests/github_operations/test_issue_manager_core.py` to
> `tests/github_operations/issues/test_manager.py`, then fold
> `tests/github_operations/issues/test_list_issues.py`'s `TestListIssuesExtendedParams`
> class into it (verbatim, deduping imports) and delete `test_list_issues.py`. No other
> logic changes; keep the `git_integration` markers. Verify with
> `mcp__tools-py__run_pytest_check`, `check_file_size(max_lines=750)`, then pylint and
> mypy. Follow all `CLAUDE.md` rules (MCP tools only; `./tools/format_all.sh` before
> committing). Produce exactly one commit.
