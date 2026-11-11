# Step 10 — Tool `git_branch_delete`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file. Implement step 10 only: tests first, then the
> tool in `toolset/git_write.py` and its orchestration in `toolset/_git_write_helpers.py`
> (reuse `guard_name`, `run_tool`, `short` from step 9). Run format, pylint, pytest
> (`-n auto`), mypy, lint-imports and ruff; all must pass. Make exactly one commit.

## WHERE

- `src/mcp_workspace/toolset/git_write.py`: closure `git_branch_delete(name)`.
- `src/mcp_workspace/toolset/_git_write_helpers.py`: `do_git_branch_delete`, `tip_on_github`.
- `tests/toolset/test_git_branch_delete.py`; `tests/toolset/test_toolset.py`;
  `tests/toolset/tool_schemas/git_branch_delete.json`.

## WHAT

```python
async def git_branch_delete(name: Annotated[str, Field(description=...)]) -> str:
    """Force-delete a local branch whose tip is on GitHub (modifies the repository). ..."""

def tip_on_github(ctx: WorkspaceContext, name: str, tip: str, default: str | None) -> tuple[str | None, bool, list[str]]:
    """Return (passing check description or None, object_missing, notes)."""

def do_git_branch_delete(ctx: WorkspaceContext, name: str) -> str: ...
```

## HOW

- Library: `get_current_branch_name`, `get_default_branch_name` (branch_queries),
  `resolve_commit`, `is_ancestor` (step 4), `remote_head_sha` (step 3),
  `delete_local_branch_force` (step 5); PR check via `pr_manager(ctx, None)` from
  `toolset/_github_common.py` and `find_merged_pr_by_head_sha` (step 8).
- PR check is wrapped in `try/except Exception` → note "merged-PR check skipped: <reason>"
  (covers no token, auth errors, network). Without a GitHub token the check is skipped.
- Description states what it refuses: current branch, default branch (`main`/`master` when the
  default is unknown), tips not on GitHub; and that it never deletes the remote branch.
- Same closure pattern as step 9 (lazy helper import, lock, `to_thread`).

## ALGORITHM

```
guard_name(name); current = get_current_branch_name(); name == current -> Error "cannot delete the current branch"
default = get_default_branch_name(); refused = {default} if default else {"main", "master"}; name in refused -> Error
tip = resolve_commit(f"refs/heads/{name}"); None -> Error "no local branch <name>"
tip_on_github: evaluate all three, stop at the first pass; is_ancestor None -> object_missing = True
  (1) r = remote_head_sha(name); r.sha -> is_ancestor(tip, r.sha);  r failed -> note r.error
  (2) default and is_ancestor(tip, f"refs/remotes/origin/{default}")   (ref missing -> object_missing)
  (3) find_merged_pr_by_head_sha(tip) -> f"merged PR #{n}"
pass  -> delete_local_branch_force -> f"Deleted branch {name} (tip {short(tip)} on origin)\nVerified by: <check>"
none  -> object_missing ? "Error: cannot verify tip <sha7> ... run git fetch first" : "Error: refusing to delete <name>: tip <sha7> is not on GitHub" (+ notes)
```

## DATA

`str`: `Deleted branch <name> (tip <sha7> on origin)` + `Verified by:` line, or `Error: ...`.

## Tests (write first)

Unit (patch library + `find_merged_pr_by_head_sha` / `pr_manager`):
- current branch, default branch, `main`/`master` when default is None → refused, no delete.
- invalid name → refused.
- check 1 passes (remote SHA contains tip) → deleted, checks 2/3 not needed.
- check 1 fails, check 2 passes → deleted.
- checks 1/2 fail, check 3 returns PR number → deleted, `Verified by: merged PR #N`.
- `is_ancestor` returns None for check 1, check 3 passes → deleted (no short-circuit on missing).
- none passes, one object missing → `fetch first` error; none missing → `not on GitHub` error.
- `pr_manager` raises (no token) → check 3 skipped, result still decided by 1/2.
- `remote_head_sha` failure → its error in the refusal notes.

Integration (`git_integration`, `origin_clone`, PR lookup patched to None):
- **squash-merged branch**: branch with own commit pushed; on `main` create a squash commit of it,
  push `main`, delete the remote branch; local branch → refused (not ancestor, no remote);
  with PR lookup patched to return 7 → deleted. Fast-forward-merged branch → deleted by check 2.
- unpushed branch → refused with "not on GitHub".
- pushed branch (remote SHA == tip) → deleted, remote branch still exists.

Snapshot + `EXPECTED`/`ASYNC_TOOLS` as in step 9.

## Commit

`feat(toolset): add git_branch_delete tool with tip-on-GitHub check`
