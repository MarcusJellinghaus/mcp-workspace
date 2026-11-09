# Step 4 — Move group `workspace.write` (`save_file`, `edit_file`, `append_file`)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md`.
> Move the three write tools into `toolset/write.py`, following the pattern of `toolset/read.py`.
> File locks move to `ctx.file_locks`. Adapt the tests first, then move the code, then delete
> what became unused. Run all checks, format, commit.

## WHERE

- `src/mcp_workspace/toolset/write.py` (new)
- `src/mcp_workspace/toolset/__init__.py` (append `write.register`)
- `src/mcp_workspace/server.py`: delete `save_file`, `append_file`, `edit_file`, `_file_locks`
- Tests, adapting only the parts for these three tools:
  - `tests/test_server.py`
  - `tests/file_tools/test_edit_file_api.py` (uses `tools` instead of `set_project_dir` + imports)
  - `tests/test_file_tool_path_rules.py`
  - `tests/test_path_separator_invariant.py` (`edit_file`)
  - Patches of `mcp_workspace.server.save_file_util` / `append_file_util` / `edit_file_util` become
    `mcp_workspace.toolset.write.*`.

## WHAT

```python
def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.write tools bound to ctx."""

    @log_function_call
    def save_file(file_path: Annotated[str, Field(...)], content: Annotated[str, Field(...)]) -> bool: ...

    @log_function_call
    def append_file(file_path: Annotated[str, Field(...)], content: Annotated[str, Field(...)]) -> bool: ...

    @log_function_call
    async def edit_file(file_path: ..., old_string: ..., new_string: ...,
                        replace_all: Annotated[bool, Field(...)] = False) -> str: ...

    for fn in (save_file, edit_file, append_file):
        sink.add(tool_spec(fn, group="workspace.write", read_only=False))
```

## HOW

- Module-level imports: `save_file_util`, `append_file_util`, `edit_file_util` (same aliases as in `server.py`).
- Bodies are copied unchanged, except:
  - `_project_dir` becomes `ctx.project_dir`;
  - `_file_locks` becomes `ctx.file_locks`;
  - `_check_not_gitignored(p)` becomes `check_not_gitignored(ctx, p)`;
  - the project-dir guards are deleted.
- `Args:` text goes into `Field` descriptions; the not-set wording comes out of `Raises:` (as in step 3).
- `edit_file` stays `async`.
- Write the new test first, in `tests/toolset/test_toolset.py`:
  - The three specs have `group == "workspace.write"` and `read_only is False`.
  - `inspect.iscoroutinefunction(spec.fn)` is true for `edit_file`.

## ALGORITHM

`edit_file`, unchanged apart from `ctx`:

```
check_not_gitignored(ctx, file_path)
abs_path = str((ctx.project_dir / file_path).resolve())
lock = ctx.file_locks.setdefault(abs_path, asyncio.Lock())
async with lock: return edit_file_util(file_path, old_string, new_string, replace_all, ctx.project_dir)
```

## DATA

6 specs from `tool_specs`; 31 tools on the server.

## Checks

Snapshot green; all checks pass. One commit:
`refactor(toolset): move workspace.write tools into toolset`.
