# Step 9 — Rebuild `rebase_onto_branch` on `rebase_start` / `rebase_abort`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_9.md` exactly.
> Tests first, then code. Run format, pylint, pytest (`-n auto`), mypy and lint-imports;
> all must pass. Make one commit:
> `refactor(remotes): build rebase_onto_branch on rebase_start/rebase_abort (#355)`.

## WHERE

- `src/mcp_workspace/git_operations/remotes.py` — imports, `rebase_onto_branch` (~line 530–613)
- `tests/git_operations/test_remotes.py` — `TestRebaseOntoBranch`
- `docs/release-notes.md` — Compatibility section

## WHAT

`rebase_onto_branch(project_dir: Path, target_branch: str) -> bool`: signature, `bool`
contract and "never raises" unchanged. It stays in `remotes.py`.

## HOW

- Add `from .rebase import rebase_abort, rebase_start`. `rebase.py` imports only `core` and
  `porcelain_parsers`, so there is no cycle.
- Keep both existing prechecks (non-repo, blank target) and the `fetch_remote` call as they
  are.
- Replace the whole `with safe_repo_context(...)` block. That removes the inline rebase-dir
  check and the "up to date" string check (up-to-date is `completed`).
- Keep the outer `except` clauses. If `GitCommandError` / `InvalidGitRepositoryError` can no
  longer be raised inside the `try`, collapse them into the existing broad
  `except Exception` (with its pylint disable). The function must never raise.
- Remove imports that become unused (`safe_repo_context` is still used elsewhere in the
  module; check before removing anything).
- Docstring: "If conflicts are detected, automatically aborts the rebase" stays. Add: "A
  rebase already in progress is left alone (returns False)." Keep the NOTE about being moved
  from `branches.py`.

## ALGORITHM

```
<unchanged prechecks; fetch_remote → False on failure>
result = rebase_start(project_dir, f"origin/{target_branch}")
if result["status"] == "completed": logger.info("Successfully rebased onto origin/%s", target_branch); return True
if result["status"] == "stopped_on_conflict":
    logger.warning("Skipping rebase: merge conflicts detected, aborting rebase")   # no dirty-tree block
    abort = rebase_abort(project_dir)
    if not abort["success"]: logger.warning("Failed to abort rebase: %s", abort["stderr"] or abort["error"])
    return False
logger.warning(f"Skipping rebase: {result['stderr'] or result['error']}{_format_dirty_tree(project_dir)}"); return False
```

## DATA

`RebaseResult`: `status` ∈ `completed | stopped_on_conflict | error`; `stderr` is None when
`rebase_start` refused without running git (e.g. a rebase already in progress), so use
`stderr or error`. `rebase_abort` → `GitResult`.

## Tests (write first)

All existing `TestRebaseOntoBranch` tests must pass **unchanged**, in particular:
- `test_rebase_onto_branch_dirty_tree_logs_files`: `"modified: README.md"` in the log.
- `test_rebase_onto_branch_conflict_in_linked_worktree`: "merge conflicts detected" present,
  "Working tree:" absent, rebase aborted, HEAD unchanged.

New `test_rebase_onto_branch_keeps_existing_rebase` (`git_repo_with_remote`):
1. Push main; build the same conflict as `test_rebase_onto_branch_conflict_aborts` (feature
   branch and main both add `conflict.txt` with different content; push main).
2. On the feature branch, start a conflicting rebase by hand:
   `repo.git.rebase(f"origin/{current_branch}")` inside `pytest.raises(GitCommandError)`.
   Record `Path(repo.git_dir) / "rebase-merge"` (or `rebase-apply`) as existing.
3. `rebase_onto_branch(project_dir, current_branch)` → `False`.
4. Assert the rebase dir still exists (the user's rebase was not aborted).
5. Clean up with `repo.git.rebase("--abort")`.

On the old code this test fails: the old code aborts the user's rebase.

## Release notes

In `docs/release-notes.md` → `### Compatibility`, replace the bullet
`` - `rebase_onto_branch` is unchanged (keeps its inline rebase-dir check until #355). `` with:

```
- `rebase_onto_branch` no longer aborts a rebase that was already in progress; it returns
  `False` and leaves it alone.
```

## Verify

Search `src/` for `rebase-merge` / `rebase-apply`: matches only in `rebase.py`.
