# Step 4 — `_format_dirty_tree` uses `get_working_tree_status`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md` exactly.
> Tests first, then code. Run format, pylint, pytest (`-n auto`), mypy and lint-imports;
> all must pass. Make one commit:
> `refactor(remotes): render dirty tree from get_working_tree_status (#355)`.

## WHERE

- `src/mcp_workspace/git_operations/remotes.py` — import line 24, `_format_dirty_tree` (~line 508)
- `tests/git_operations/test_remotes.py` — `TestFormatDirtyTree` (~line 443–479)

## WHAT

`_format_dirty_tree(project_dir: Path) -> str`: signature and output unchanged.

## HOW

- Import: `from .repository_status import get_working_tree_status, is_git_repository`
  (`get_full_status` is no longer used in `remotes.py`).
- Replace `status = get_full_status(project_dir)` with
  `status = get_working_tree_status(project_dir)`. A failed `StatusResult` already has empty
  lists, so the existing loop returns `""` on failure with no extra branch. Add one sentence
  to the docstring: "Also empty when the status could not be read."

## ALGORITHM

Unchanged loop over `("staged", "modified", "untracked")` reading `status[label]`.

## DATA

Input: `StatusResult` (`success`, `error`, `returncode`, `stderr`, `clean`, `staged`,
`modified`, `untracked`). Output: `""` or `"\nWorking tree:\n  <label>: ..."`.

## Tests (write first)

In `TestFormatDirtyTree`:
- Patch target in all three tests →
  `"mcp_workspace.git_operations.remotes.get_working_tree_status"`.
- Add a module-level helper that builds a successful `StatusResult` from the three lists
  (`success=True, error=None, returncode=0, stderr="", clean=not any(lists)`), and return it
  from the mocks.
- New `test_format_dirty_tree_status_failure`: the mock returns a failed `StatusResult`
  (`success=False, error="git status failed (exit 128)", clean=False`, empty lists) →
  `_format_dirty_tree(...) == ""`.

`TestRebaseOntoBranch.test_rebase_onto_branch_dirty_tree_logs_files` must still pass
unchanged.
