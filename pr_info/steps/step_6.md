# Step 6 — Move group `workspace.move` (`move_file`)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_6.md`.
> Move `move_file` into `toolset/move.py`, following the pattern of `toolset/delete.py`.
> Adapt the tests first, then move the code, then delete what became unused.
> Run all checks, format, commit.

## WHERE

- `src/mcp_workspace/toolset/move.py` (new)
- `src/mcp_workspace/toolset/__init__.py` (append `move.register`)
- `src/mcp_workspace/server.py`: delete `move_file`
  - `_check_not_gitignored` stays, because `_resolve_body` still uses it until step 10.
- Tests:
  - `tests/test_server.py`, lines 219–245:
    - `@patch("mcp_workspace.server.move_file_util")` becomes `mcp_workspace.toolset.move.move_file_util`;
    - the local import `move_file as move_file_fn` becomes `tools["move_file"]`.
  - `tests/test_file_tool_path_rules.py`: the move entries. After this step the file no longer
    needs `server`; its `monkeypatch.setattr(server, "_project_dir", root)` setup becomes `make_tools(root)`.

## WHAT

```python
def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.move tool bound to ctx."""

    @log_function_call
    def move_file(source_path: Annotated[str, Field(...)],
                  destination_path: Annotated[str, Field(...)]) -> bool: ...

    sink.add(tool_spec(move_file, group="workspace.move", read_only=False))
```

## HOW

- Module-level import: `move_file as move_file_util`.
- Body is copied unchanged, including the error-simplification `except` chain, except:
  - `_project_dir` becomes `ctx.project_dir`;
  - the guard is deleted;
  - `check_not_gitignored(ctx, ...)` is used for source and destination.
- Write the new test first, in `tests/toolset/test_toolset.py`: group `workspace.move`, `read_only is False`.

## ALGORITHM

No new logic.

## DATA

9 specs from `tool_specs`; 31 tools on the server.

## Checks

Snapshot green; all checks pass. One commit:
`refactor(toolset): move workspace.move tool into toolset`.
