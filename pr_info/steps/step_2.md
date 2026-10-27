# Step 2 — `_detect_from_merge_base` uses `probe_origin_branch`; delete `origin_has_branch`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md` exactly.
> Tests first, then code. Run format, pylint, pytest (`-n auto`), mypy, lint-imports and
> vulture; all must pass. Make one commit:
> `refactor(base_branch): drop origin_has_branch, use probe_origin_branch (#355)`.

## Precondition

`src/mcp_workspace/server.py` no longer references `origin_has_branch` (step 1). If it
still does, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/git_operations/base_branch.py` — delete `origin_has_branch` (~line 133),
  edit `_detect_from_merge_base` (~line 196–203)
- `tests/git_operations/test_base_branch_git.py`
- `tests/git_operations/test_remote_queries.py`
- `docs/release-notes.md` — Compatibility section

## WHAT

- Delete `origin_has_branch(project_dir, branch_name) -> bool`.
- `_detect_from_merge_base(project_dir, current_branch) -> Optional[str]`: signature and
  docstring contract unchanged.

## HOW

- `probe_origin_branch` is already imported in `base_branch.py` from `.remotes`.
- Remove `from git.exc import GitCommandError` (only `origin_has_branch` used it).
- Keep the existing `except Exception` around the single call.

## ALGORITHM

```
try:
    probe = probe_origin_branch(project_dir, result)
except Exception as e:                       # existing broad catch, scoped to the call
    logger.debug("Could not ask origin about branch '%s': %s", result, e); return result
if probe["exists"] is None:
    logger.debug("Could not ask origin about branch '%s': %s", result, probe["stderr"] or probe["error"]); return result
if not probe["exists"]:
    logger.debug("Discarding merge-base winner ..."); return None
return result
```

## DATA

`BranchProbe.exists`: True → keep the winner, False → discard (`None`), None → keep the
winner.

## Tests (write first)

`test_base_branch_git.py`:
- Remove `origin_has_branch` from the import.
- `test_default_branch_winner_skips_the_remote_check`: rename the patch target to
  `"mcp_workspace.git_operations.base_branch.probe_origin_branch"`. `_record` returns a
  `BranchProbe` dict (`success=True, error=None, returncode=0, stderr="", exists=True`);
  annotate its return as `BranchProbe` (import from `mcp_workspace.git_operations.core`).
- Delete `test_origin_has_branch_true_for_pushed_branch`,
  `test_origin_has_branch_false_for_absent_branch` and
  `test_origin_has_branch_raises_when_origin_unreachable` (~line 125–158).
  `test_winner_deleted_upstream_falls_back_to_default_branch`,
  `test_winner_still_on_origin_is_kept` and `test_unreachable_origin_keeps_the_winner`
  already cover the three `exists` outcomes against real git. They stay unchanged and must
  pass.

`test_remote_queries.py`:
- Delete `TestOriginHasBranchWrapper` and the `origin_has_branch` import. Drop the
  `GitCommandError` import if it becomes unused. Module docstring: remove "its wrapper".

## Release notes

In `docs/release-notes.md` → `### Compatibility`, delete the `origin_has_branch raises
GitCommandError ...` bullet (two lines, ~80–81). Leave the `rebase_onto_branch` bullet for
step 9.

## Verify

Search `src/` and `tests/` for `origin_has_branch`: no matches.
