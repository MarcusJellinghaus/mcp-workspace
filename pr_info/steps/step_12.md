# Step 12 — Tool `git_push`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file. Implement step 12 only: tests first, then the
> tool and its orchestration (reuse step 9 helpers). Run format, pylint, pytest (`-n auto`),
> mypy, lint-imports and ruff; all must pass. Make exactly one commit.

## WHERE

- `src/mcp_workspace/toolset/git_write.py`: closure `git_push()` (no arguments).
- `src/mcp_workspace/toolset/_git_write_helpers.py`: `guard_push_branch`, `do_git_push`.
- `tests/toolset/test_git_push.py`; `tests/toolset/test_toolset.py`;
  `tests/toolset/tool_schemas/git_push.json`.

## WHAT

```python
async def git_push() -> str:
    """Push the current branch to origin with upstream tracking (modifies the remote). ..."""

def guard_push_branch(project_dir: Path) -> tuple[str | None, str | None]:
    """Return (branch, None) or (None, "Error: ...")."""

def do_git_push(ctx: WorkspaceContext, force: bool = False) -> str: ...
```

`do_git_push` takes `force` so step 13 reuses it.

## HOW

- Library: `get_current_branch_name`, `get_default_branch_name`, `push_current_branch` (step 2).
- The closure is named `git_push`; it imports only `_git_write_helpers` lazily, so the library's
  `git_operations.git_push` is never shadowed.
- Description: modifies the remote; always `-u origin`, current branch only; refuses detached
  HEAD and the default branch; never forces; no arguments.
- Same closure pattern as step 9.

## ALGORITHM

```
branch = get_current_branch_name(); None -> "Error: HEAD is detached; check out a branch first"
default = get_default_branch_name(); None -> "Error: cannot determine the default branch (no origin/HEAD, no main/master); set it with git remote set-head origin -a"
branch == default -> f"Error: refusing to push the default branch {branch}"
r = push_current_branch(dir, force)
ok -> (f"Force-pushed {branch} to origin (lease ok)" if force else f"Pushed {branch} to origin") + ("\n" + r.stderr.strip() if r.stderr)
fail -> f"Error: {r.error}" + ("\n" + r.stderr.strip() if r.stderr)
```

## DATA

`str`: `Pushed <b> to origin`, then git's (scrubbed) push output; or `Error: ...`.

## Tests (write first)

Unit (patch library functions where `_git_write_helpers.py` imports them, e.g.
`mcp_workspace.toolset._git_write_helpers.push_current_branch` — not in `mcp_workspace.git_operations.*`):
- detached HEAD → error; default branch → error; default unknown → error with hint; push not called.
- push rejected → `Error:` with git's stderr.
- timeout from the library → `Error: git push timed out after 120 s`.
- success → first line `Pushed <b> to origin`, followed by the library's `stderr`.

Integration (`git_integration`, `origin_clone`):
- new branch with a commit → `Pushed <b> to origin`; the bare origin has the branch; upstream set.
- a tag with the branch's name exists → push succeeds.
- on `main` → refused.
- remote advanced by another clone (`make_clone`) → non-fast-forward `Error:`.

Snapshot + `EXPECTED`/`ASYNC_TOOLS` as in step 9.

## Commit

`feat(toolset): add git_push tool`
