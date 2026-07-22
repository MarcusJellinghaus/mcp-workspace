# Summary — Issue #222: Mirror issue-manager tests to `issues/` + split oversized test files

## Goal

Reorganize the **tests** for the `github_operations/issues/` source package so the test
tree mirrors the source **namespace** (one source module → one test namespace), fold the
existing function-focused `issues/` tests into their module mirror, split the three
oversized test files so every test file is **under 750 lines**, and remove their entries
from `.large-files-allowlist`.

This is a **test-only** change. No production code under `src/` is modified. Two bounded
new-coverage additions are in scope: `parse_base_branch` and `create_empty_issue_data`.

## Architectural / design changes

There is **no change to the production architecture, import graph, or runtime behavior.**
This is a change to the *test-suite topology* only:

- **Test namespace now mirrors the source package.** Every module in
  `src/mcp_workspace/github_operations/issues/` gets a matching test namespace under
  `tests/github_operations/issues/` (1 test namespace per source module; a module whose
  tests exceed 750 lines is a **prefixed multi-file split**, e.g. `test_cache_*.py`).
  This improves discoverability (find a module's tests by name) and makes the
  test-to-source mapping explicit.
- **Maintainability gate satisfied without exceptions.** All three oversized files come
  off `.large-files-allowlist`; the ≤750-line rule is met by real splits, not waivers.
- **No architecture-enforcement impact.** Tests are leaf nodes and already independent;
  the import-linter "test independence" contract and `tach` layering are unaffected
  (imports still come from `mcp_workspace.github_operations.issues`).
- **Fixtures unchanged.** Cache/manager fixtures cascade from the parent
  `tests/github_operations/conftest.py`; `issues/conftest.py` adds `mock_manager`. pytest
  inherits the parent conftest into `issues/`, so relocated tests keep working with **no
  fixture changes**.

## Guiding principle (KISS)

The task is ~90% mechanical: **rename/relocate healthy files, split two big files by
*whole test class*, add two tiny new test files, drop three allowlist lines.**

- **One splitting rule:** pack *whole test classes* into files; never cut inside a class.
  File names come from the dominant class's concern. The **only** forced exception is the
  single ~810-line class `TestGetBranchWithPRFallback`, which exceeds 750 on its own and
  must be divided by method group.
- **Move, don't change:** no test-logic edits except the two bounded additions.
- **Prefer `move_file` (git mv)** for pure renames so history/blame and diffs stay clean.

## Target test tree (`tests/github_operations/issues/`)

```
test_base.py                    # base.py — moved validate_* tests + NEW parse_base_branch
test_types.py                   # types.py — NEW, create_empty_issue_data only
test_branch_naming.py           # branch_naming.py — relocated flat file
test_comments_mixin.py          # comments_mixin.py
test_labels_mixin.py            # labels_mixin.py
test_events_mixin.py            # events_mixin.py
test_manager.py                 # manager.py (folds test_list_issues.py)
test_manager_integration.py
test_branch_manager_*.py        # branch_manager.py — by-concern split (folds 3 files)
test_branch_manager_integration.py
test_cache_*.py                 # cache.py — by-concern split
```

## Implementation steps (each = exactly one commit)

| Step | Title | Kind |
|------|-------|------|
| 1 | Relocate the six healthy test files into `issues/` | pure rename (git mv) |
| 2 | Create `test_types.py` (`create_empty_issue_data`) | TDD, new coverage |
| 3 | Create `test_base.py` (extract `validate_*` + NEW `parse_base_branch`) | TDD, new coverage + move |
| 4 | Create `test_manager.py` (rename core, fold `test_list_issues.py`) | rename + fold |
| 5 | Split `test_issue_cache.py` → `test_cache_*.py` + drop allowlist line | split |
| 6 | Split `test_issue_branch_manager.py` (+fold 3) → `test_branch_manager_*.py` + drop 2 allowlist lines | split |

Dependencies: Step 4 must follow Step 3 (both touch the core file). Steps 1, 2, 3, 5, 6
are otherwise independent. Recommended order: 1 → 2 → 3 → 4 → 5 → 6.

## Files / folders created or modified

**Created (test files):**
- `tests/github_operations/issues/test_types.py` (Step 2)
- `tests/github_operations/issues/test_base.py` (Step 3)
- `tests/github_operations/issues/test_cache_*.py` — 4–5 files (Step 5)
- `tests/github_operations/issues/test_branch_manager_*.py` — 4–5 files (Step 6)

**Created via rename / relocation (`move_file`):**
- `test_branch_naming.py`, `test_comments_mixin.py`, `test_labels_mixin.py`,
  `test_events_mixin.py`, `test_manager_integration.py`,
  `test_branch_manager_integration.py` (Step 1)
- `test_manager.py` (from `test_issue_manager_core.py`, Step 4)

**Modified:**
- `tests/github_operations/test_issue_manager_core.py` — `validate_*` tests removed
  (Step 3), then renamed/folded into `issues/test_manager.py` (Step 4)
- `.large-files-allowlist` — remove the three issue entries (Steps 5 & 6);
  **retain** `test_base_manager.py`, `test_github_utils.py`, `test_verification.py`

**Deleted (content folded/split elsewhere):**
- `tests/github_operations/test_issue_cache.py` (Step 5)
- `tests/github_operations/test_issue_branch_manager.py` (Step 6)
- `tests/github_operations/issues/test_get_branch_with_pr_fallback.py` (Step 6)
- `tests/github_operations/issues/test_extract_prs_by_states.py` (Step 6)
- `tests/github_operations/issues/test_search_branches_by_pattern.py` (Step 6)
- `tests/github_operations/issues/test_list_issues.py` (Step 4)

**Not touched:** anything under `src/`; `conftest.py` files; the three non-issue allowlist
entries.

## Verification (run after every step)

Per `CLAUDE.md`, use MCP tools only:
1. `mcp__tools-py__run_pytest_check` on the affected path **including** git markers
   (many of these tests are `@pytest.mark.git_integration`), e.g.
   `extra_args=["-n","auto","tests/github_operations/issues"]`, plus a repo-wide
   `--collect-only` to catch collection/import breakage.
2. `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_mypy_check`.
3. For split steps (5, 6): `mcp__mcp-workspace__check_file_size(max_lines=750)` — every
   file under 750 and off the allowlist.
4. Before commit: `./tools/format_all.sh`.

## Acceptance criteria (from the issue)

- [ ] Test tree mirrors `issues/` source package (1:module namespace), incl. `test_branch_naming.py`
- [ ] All three oversized files split; every test file < 750 lines
- [ ] The three issue entries removed from `.large-files-allowlist`; three non-issue entries retained
- [ ] Function-focused `issues/` tests folded into module-mirror files
- [ ] `test_base.py` exists: moved `validate_*` + new `parse_base_branch` tests
- [ ] `test_types.py` exists covering `create_empty_issue_data`
- [ ] No test-logic changes beyond the two bounded additions
- [ ] `pytest` collection finds all tests; all pass
- [ ] `lint-imports` / `tach check` pass
