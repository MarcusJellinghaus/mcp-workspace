# Step 6 — Split branch-manager tests → `test_branch_manager_*.py` (fold 3) + drop 2 allowlist lines

> Read `pr_info/steps/summary.md` first. This is Step 6 of 6. One commit.

## Kind
Test-only split by **whole test class**, absorbing three folded files. Source
(`branch_manager.py`) stays as-is. Combined input ≈ 2264 lines → **4–5 files**, each < 750.
**No test-logic changes.**

## WHERE
- Delete (contents folded/split here):
  - `tests/github_operations/test_issue_branch_manager.py` (1189)
  - `tests/github_operations/issues/test_get_branch_with_pr_fallback.py` (~825)
  - `tests/github_operations/issues/test_extract_prs_by_states.py` (107)
  - `tests/github_operations/issues/test_search_branches_by_pattern.py` (143)
- Create: `tests/github_operations/issues/test_branch_manager_*.py` (4–5 files)
- Modify: `.large-files-allowlist` — remove these two lines:
  - `tests/github_operations/test_issue_branch_manager.py`
  - `tests/github_operations/issues/test_get_branch_with_pr_fallback.py`

## WHAT — packing rule + the one forced exception
Pack whole classes by concern; never cut inside a class — **except**
`TestGetBranchWithPRFallback`, which is ~810 lines and exceeds 750 on its own. It is the
**only** class that must be divided, split by method group into two files. Suggested
grouping (finalize from actual sizes; each < 750):

| File | Classes |
|---|---|
| `test_branch_manager_linked.py` | `TestGetLinkedBranches`, `TestDeleteLinkedBranch` |
| `test_branch_manager_create.py` | `TestCreateLinkedBranch` |
| `test_branch_manager_pr_fallback_a.py` | `TestGetBranchWithPRFallback` — first method group |
| `test_branch_manager_pr_fallback_b.py` | `TestGetBranchWithPRFallback` — remaining methods |
| `test_branch_manager_resolution.py` | `TestExtractPrsByStates`, `TestSearchBranchesByPattern` (+ helper `_make_git_ref`) |

(Names are by-concern, not numbered; `pr_fallback_a/b` reflect a single forced intra-class
split. Regroup freely as long as every file is < 750 and no class other than
`TestGetBranchWithPRFallback` is divided.)

## HOW — imports / fixtures
Each new file repeats only the imports its classes need (e.g.
`from mcp_workspace.github_operations.issues import IssueBranchManager`). The `mock_manager`
fixture lives in `issues/conftest.py` and is inherited — **unchanged**. Keep helper
`_make_git_ref` with the class that uses it. When splitting `TestGetBranchWithPRFallback`,
both halves keep the same class name and duplicate only the shared setup/imports they each
need; do not alter method bodies.

## ALGORITHM
```
list classes + line ranges across the 4 source files
assign whole classes to target files by concern
for TestGetBranchWithPRFallback: partition its methods into two files (same class name)
write each target file: needed imports + assigned classes/methods verbatim
delete the 4 source files
remove the 2 issue lines from .large-files-allowlist
check_file_size(750): every new file < 750, none allowlisted
```

## DATA
No new data structures. Deliverable = 4–5 `test_branch_manager_*.py` files (verbatim
bodies) + trimmed allowlist.

## Verify (MCP tools only)
- `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","tests/github_operations/issues"])`
  (keep git markers) — total branch-manager test count preserved, all pass.
- `mcp__mcp-workspace__check_file_size(max_lines=750)` — all `test_branch_manager_*.py`
  < 750; the two originals no longer flagged/allowlisted.
- Confirm `.large-files-allowlist` now contains **zero** issue-test entries but still lists
  `test_base_manager.py`, `test_github_utils.py`, `test_verification.py`.
- `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","--collect-only"])`,
  `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_mypy_check`,
  `mcp__tools-py__run_tach_check`, `mcp__tools-py__run_lint_imports_check`.

## Done when
All branch-manager tests live in `test_branch_manager_*.py` files under 750, the four
source files and both allowlist lines are gone, full suite collects and passes, tach /
lint-imports green. One commit — completes the issue.

## LLM prompt
> Implement Step 6 from `pr_info/steps/step_6.md` (context in `pr_info/steps/summary.md`).
> Split `tests/github_operations/test_issue_branch_manager.py` and fold
> `issues/test_get_branch_with_pr_fallback.py`, `issues/test_extract_prs_by_states.py`,
> `issues/test_search_branches_by_pattern.py` into 4–5
> `tests/github_operations/issues/test_branch_manager_*.py` files by **whole test class**,
> copying bodies and needed imports **verbatim**. The only class you may divide is
> `TestGetBranchWithPRFallback` (~810 lines) — split it by method group into two files that
> share the class name. Delete the four source files and remove the two issue lines from
> `.large-files-allowlist` (keep the three non-issue entries). Verify with
> `mcp__tools-py__run_pytest_check`, `check_file_size(max_lines=750)`, a repo-wide
> `--collect-only`, then pylint, mypy, tach, and lint-imports. Follow all `CLAUDE.md` rules
> (MCP tools only; `./tools/format_all.sh` before committing). Produce exactly one commit.
