# Step 8 — Move group `workspace.git` (`git`)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_8.md`.
> Move the `git` tool into `toolset/git.py`, keeping the lazy GitPython import inside the tool body.
> Adapt the tests first, then move the code, then delete what became unused.
> Run all checks, format, commit.

## WHERE

- `src/mcp_workspace/toolset/git.py` (new)
- `src/mcp_workspace/toolset/__init__.py` (append `git.register`)
- `src/mcp_workspace/server.py`: delete `git`
- `src/mcp_workspace/server_reference_tools.py`: delete `get_reference_project_path` and the
  `ensure_available` import (no remaining user)
- Tests:
  - `tests/test_reference_projects_git.py`:
    - `from mcp_workspace.server import git` becomes `tools["git"]` / `make_tools(...)`;
    - the patch of `mcp_workspace.server.get_reference_project_path` becomes
      `mcp_workspace.toolset.git.reference_project_path`;
    - the test that wrote `server_module._project_dir` uses `make_tools(test_dir)`.
  - `tests/test_server.py`: git tests use `tools["git"]`. Delete the `_project_dir is None` test for
    `git` (lines 483–493); this is one of the issue's listed exceptions.
  - `tests/test_reference_projects_mcp_tools.py`, `TestGetReferenceProjectPath` (633–686), converted in
    this step because it deletes `get_reference_project_path`:
    - call `await reference_project_path(ctx, name)` from `mcp_workspace.toolset.reference`, with
      `ctx = WorkspaceContext(tmp_path, {"test_proj": proj}, None, None, False, True)` (`{}` for the
      not-found case) instead of writing `server_module._reference_projects`;
    - the `ensure_available` patches become `mcp_workspace.toolset.reference.ensure_available`;
    - assertions unchanged.
  - `tests/test_tool_refusals_mcp_layer.py`: no change needed, because it goes through `create_server` (step 2).
  - `tests/github_operations/test_github_read_tools_reference.py:149` and
    `test_github_write_tools_reference.py:193` patch `mcp_workspace.server_reference_tools.ensure_available`,
    which no longer exists. Retarget them to `mcp_workspace.toolset.reference.ensure_available`;
    their assertions are unchanged.

## WHAT

```python
def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    @log_function_call
    async def git(
        command: Annotated[str, Field(...)],
        args: Annotated[list[str] | None, Field(...)] = None,
        pathspec: Annotated[list[str] | None, Field(...)] = None,
        search: Annotated[str | None, Field(...)] = None,
        context: Annotated[int, Field(...)] = 3,
        max_lines: Annotated[int | None, Field(...)] = None,
        compact: Annotated[bool, Field(...)] = True,
        reference_name: Annotated[str | None, Field(...)] = None,
    ) -> str: ...

    sink.add(tool_spec(git, group="workspace.git", read_only=True))
```

## HOW

- `from mcp_workspace.toolset.reference import reference_project_path` at module level. This is the
  patch target `mcp_workspace.toolset.git.reference_project_path`.
- Keep `from mcp_workspace.git_operations.read_operations import git as git_impl` *inside*
  the tool body (lazy import, relied on by #379).
- Delete the `Raises:` section, which only described the project-dir guard, and the guard itself.
- `read_only=True`, as decided in the issue: `fetch` only writes `.git`, never the working tree.
- Write the new test first, in `tests/toolset/test_toolset.py`:
  - The `git` spec has group `workspace.git` and `read_only is True`.
  - It is a coroutine function.

## ALGORITHM

```
from mcp_workspace.git_operations.read_operations import git as git_impl   # lazy
project_dir = await reference_project_path(ctx, reference_name) if reference_name is not None else ctx.project_dir
return await asyncio.to_thread(git_impl, command=command, project_dir=project_dir, args=args, ...)
```

## DATA

14 specs from `tool_specs`; 31 tools on the server.

## Checks

Snapshot green; all checks pass. `test_startup_performance.py` is still green (no eager git import).
One commit: `refactor(toolset): move workspace.git tool into toolset`.
