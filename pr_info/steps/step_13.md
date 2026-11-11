# Step 13 — Tool `git_push_force`

## LLM prompt

> Read `pr_info/steps/summary.md` (design point 7) and this file. Implement step 13 only:
> tests first, then the tool (it reuses `do_git_push(ctx, force=True)` from step 12). Run
> format, pylint, pytest (`-n auto`), mypy, lint-imports and ruff; all must pass. Make exactly
> one commit.

## WHERE

- `src/mcp_workspace/toolset/git_write.py`: closure `git_push_force()` (no arguments).
- `tests/toolset/test_git_push_force.py`; `tests/toolset/test_toolset.py`;
  `tests/toolset/tool_schemas/git_push_force.json`.

## WHAT

```python
async def git_push_force() -> str:
    """Force-push the current branch after a simple rebase (modifies the remote). ..."""
```

## HOW

- Body: lazy helper import, lock, `asyncio.to_thread(helpers.do_git_push, ctx, True)`.
- Description says what it refuses: detached HEAD, the default branch, git < 2.30, a remote
  branch moved by someone else since it was last fetched into this clone, and a fresh clone
  whose `origin/<branch>` has no reflog. Always `--force-with-lease --force-if-includes`, never
  plain `--force`; for anything else use Bash (manual approval).
- No new library or helper code: the version and reflog preconditions live in
  `push_current_branch(force=True)` (step 2).

## ALGORITHM

```
same as git_push (step 12) with force=True
```

## DATA

`str`: `Force-pushed <b> to origin (lease ok)` + push output, or `Error: ...`.

## Tests (write first)

Unit: default branch / detached → refused; `push_current_branch` called with `force=True`;
its version / reflog errors are passed through as `Error:`.

Integration (`git_integration`; use `origin_clone` + `make_clone`):
- **normal rebase after a push**: in clone A push branch `b`, then `main` advances (via clone B,
  A fetches), A rebases `b` onto `origin/main` → `git_push_force` succeeds.
- **remote advanced by another clone, then fetched**: A pushed `b`; B fetches `b`, commits,
  pushes; A fetches, rewrites `b` locally (amend) → refused (`Error:`), origin's `b` is still B's commit.
- **fresh clone (no reflog)**: a new clone checks out `b` from origin, amends, `git_push_force`
  → refused with the reflog message.
  **Precondition:** if the fresh clone already has a reflog for `refs/remotes/origin/b`
  (`git reflog exists` exits 0), write one line to `pr_info/.blocked.txt` and stop.
- on `main` → refused.

Split across files if `test_git_push_force.py` approaches 750 lines.

Snapshot + `EXPECTED`/`ASYNC_TOOLS` as in step 9.

## Commit

`feat(toolset): add git_push_force tool`
