# Step 9 — Tool `git_branch` (+ `git_write.py`, helpers module, lock)

## LLM prompt

> Read `pr_info/steps/summary.md` (design points 1–3) and this file. Implement step 9 only:
> tests first, then the toolset changes. Steps 1–8 provide the library functions. Run format,
> pylint, pytest (`-n auto`), mypy, lint-imports and ruff; all must pass. Make exactly one commit.

## WHERE

- `src/mcp_workspace/toolset/_context.py`: add
  `git_write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)` (+ docstring attribute).
- New `src/mcp_workspace/toolset/git_write.py`: `register(sink, ctx)` with the `git_branch` closure.
- New `src/mcp_workspace/toolset/_git_write_helpers.py`: shared guards + `do_git_branch`.
- `src/mcp_workspace/toolset/__init__.py`: import `git_write`; add `git_write.register` to
  `_GROUPS` right after `git.register`.
- New `tests/toolset/test_git_branch.py`.
- `tests/toolset/test_toolset.py`: `EXPECTED["git_branch"] = ("workspace.git", False)`; add to `ASYNC_TOOLS`.
- New `tests/toolset/tool_schemas/git_branch.json`.

## WHAT

```python
# git_write.py (closure inside register)
@log_function_call
async def git_branch(
    name: Annotated[str, Field(description=...)],
    create: Annotated[bool, Field(description=...)] = False,
    base: Annotated[str | None, Field(description=...)] = None,
) -> str:
    """Switch to a branch, or create one (modifies the repository). ..."""

# _git_write_helpers.py
def guard_operation(project_dir: Path) -> str | None: ...       # "Error: ... rebase in progress" or None
def guard_name(project_dir: Path, name: str, what: str) -> str | None: ...
def short(sha: str) -> str: ...                                  # sha[:7]
def run_tool(fn: Callable[[], str]) -> str: ...                  # exception -> "Error: <scrubbed msg>"
def do_git_branch(ctx: WorkspaceContext, name: str, create: bool, base: str | None) -> str: ...
```

## HOW

- Closure body (same pattern for every git-write tool):
  ```python
  from mcp_workspace.toolset import _git_write_helpers as helpers   # lazy: keeps GitPython off startup
  async with ctx.git_write_lock:
      return await asyncio.to_thread(helpers.do_git_branch, ctx, name, create, base)
  ```
- `sink.add(tool_spec(git_branch, group="workspace.git", read_only=False))`.
- `_git_write_helpers.py` imports from `mcp_workspace.git_operations.<module>` at top level
  (never from the package `__init__`); it is only imported lazily, so startup stays light
  (`tests/toolset/test_toolset_imports.py` must still pass).
- `run_tool` wraps each `do_*` body: catches `Exception` (pylint disable with reason "tool
  boundary: tools never raise"), returns `f"Error: {scrub_credentials(str(e))}"`.
- Description says plainly that the tool modifies the repository, never fetches, and that
  `base` accepts a local branch or `origin/<branch>` only (no SHAs, no tags).

## ALGORITHM (`do_git_branch`)

```
if base is not None and not create: return "Error: base requires create=True"
err = guard_name(name, "name") or (base and guard_name(base, "base")) or guard_operation(); if err: return err
if not create:
    r = switch_branch(project_dir, name); return f"Switched to {name}" if ok else f"Error: {r['error']}\n{r['stderr']}"
if resolve_base_ref(project_dir, f"origin/{name}"): return f"Error: origin/{name} already exists; use git_branch(name, create=False)"
start = resolve_base_ref(project_dir, base) if base else None; base given and start None -> "Error: base '<b>' is not a local branch or origin/<branch>"
r = create_and_switch_branch(project_dir, name, start, no_track=bool(start and start.startswith("refs/remotes/")))
return f"Created {name} from {base or 'HEAD'} ({short(resolve_commit(project_dir, 'HEAD'))})" or Error
```

`guard_name`: `is_valid_branch_name_strict` false → `f"Error: invalid branch {what}: {value!r}"`.
`guard_operation`: `operation_in_progress` → `f"Error: a {op} is in progress; finish or abort it first"`.

## DATA

`str`; first line `Switched to <name>` / `Created <name> from <base|HEAD> (<sha7>)` / `Error: ...`.

## Fixtures

Reuse `origin_clone` / `make_clone` from `tests/conftest.py` (introduced in step 2); no new
fixtures in this step.

## Tests (write first)

Unit (patch the library functions where `_git_write_helpers.py` imports them, e.g.
`mcp_workspace.toolset._git_write_helpers.switch_branch` — **not** at their defining module
`mcp_workspace.git_operations.*`, whose patch would not reach the helper's bound name; call via
`asyncio.run(spec.fn(...))`):
- invalid `name` (`-x`, `@{-1}`, `a..b`) → `Error: invalid branch name`, no mutation called.
- `base` given with `create=False` → `Error: base requires create=True`, no git call.
- invalid `base` → error; `base` not resolvable → error.
- rebase/merge in progress → error.
- `create=True` and `origin/<name>` exists → error pointing to `create=False`.
- `create=True, base="origin/main"` → `no_track=True` passed; `base="main"` → `no_track=False`.
- library exception → `Error: ...`, nothing raised.

Integration (`git_integration`, `origin_clone`):
- create from HEAD, then `create=False` back to `main` → `Switched to main`.
- `create=False` for a branch only on origin → tracking branch created.
- typo with `create=False` → `Error ... run git fetch first`, no branch created.
- `create=True, base="origin/main"` → upstream not set.

Toolset tests: `EXPECTED`/`ASYNC_TOOLS` updated. Snapshot: produce `git_branch.json` with a
`.scratch/` probe that calls `_current_schemas` from `test_tool_schema_snapshot.py` and prints the
`git_branch` entry, format it like `git.json`, then delete `.scratch/`.

## Commit

`feat(toolset): add git_branch tool`
