# Step 5 — Move group `workspace.delete` (`delete_this_file`, `delete_directory`)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md`.
> Move the two delete tools into `toolset/delete.py`, following the pattern of `toolset/write.py`.
> Adapt the tests first, then move the code, then delete what became unused.
> Run all checks, format, commit.

## WHERE

- `src/mcp_workspace/toolset/delete.py` (new)
- `src/mcp_workspace/toolset/__init__.py` (append `delete.register`)
- `src/mcp_workspace/server.py`: delete `delete_this_file` and `delete_directory`
- Tests, adapting only the parts for these two tools:
  - `tests/test_server.py`
  - `tests/test_file_tool_path_rules.py`
  - Patches of `mcp_workspace.server.delete_file_util` / `delete_directory_util` become `mcp_workspace.toolset.delete.*`.

## WHAT

```python
def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.delete tools bound to ctx."""

    @log_function_call
    def delete_this_file(file_path: Annotated[str, Field(...)]) -> bool: ...

    @log_function_call
    def delete_directory(dir_path: Annotated[str, Field(...)],
                         recursive: Annotated[bool, Field(...)] = False) -> list[str]: ...

    for fn in (delete_this_file, delete_directory):
        sink.add(tool_spec(fn, group="workspace.delete", read_only=False))
```

## HOW

- Module-level imports: `delete_file as delete_file_util` and `delete_directory as delete_directory_util`.
- Bodies are copied unchanged, except:
  - `_project_dir` becomes `ctx.project_dir`;
  - the gitignore check becomes `check_not_gitignored(ctx, ...)`;
  - the guards are deleted.
- `Args:` text goes into `Field` descriptions.
- Write the new test first, in `tests/toolset/test_toolset.py`: group `workspace.delete`, `read_only is False`.

## ALGORITHM

No new logic.

## DATA

8 specs from `tool_specs`; 31 tools on the server.

## Checks

Snapshot green; all checks pass. One commit:
`refactor(toolset): move workspace.delete tools into toolset`.
