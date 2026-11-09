# Step 7 — Move group `workspace.reference` (4 reference tools)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_7.md`.
> Move the four reference tools from `server_reference_tools.py` into `toolset/reference.py`,
> with reference lookups as ctx-taking module functions. Keep in
> `server_reference_tools.py` only what the legacy git/GitHub tools in `server.py` still use.
> Adapt the tests first, then move the code. Update import-linter, tach and ruff config.
> Run all checks, format, commit.

## WHERE

- `src/mcp_workspace/toolset/reference.py` (new)
- `src/mcp_workspace/toolset/__init__.py` (append `reference.register`)
- `src/mcp_workspace/server_reference_tools.py`:
  - Delete the 4 tools, `register`, `_read_max_lines`, `set_reference_read_max_lines`,
    the `FastMCP` import and the now-unused imports.
  - Keep `_reference_projects`, `set_reference_projects`, `get_reference_project_path` and `get_reference_repo_url`.
- `src/mcp_workspace/server.py`:
  - `create_server` no longer calls `register_reference_tools`.
  - `_configure_legacy` no longer calls `set_reference_read_max_lines`.
- `.importlinter`: in `mcp_library_isolation`, delete `mcp_workspace.server_reference_tools -> mcp`
  (an unmatched ignore fails import-linter). The ignore list is now `server` only.
- `tach.toml`:
  - `server_reference_tools` `depends_on` keeps only what it still imports.
  - `toolset` `depends_on` includes `mcp_workspace.utils` (`scrub_credentials`).
- `pyproject.toml`: add `"src/mcp_workspace/toolset/reference.py" = ["DOC502"]`. The old
  `server_reference_tools.py` entry is removed in step 10, together with the file.
- Tests:
  - `tests/test_reference_projects_mcp_tools.py`, `tests/test_reference_search_mcp_tools.py`,
    `tests/test_reference_path_rules.py`, `tests/test_credential_scrubbing.py` (103–110),
    `tests/test_path_separator_invariant.py` (reference part) and `tests/test_tool_descriptions.py`
    (`search_reference_files` case, same `Field`-based check as step 3).
  - Patch targets move from `mcp_workspace.server_reference_tools.<name>` to `mcp_workspace.toolset.reference.<name>`.
    This covers `ensure_available`, `read_file_util`, `list_files_util`, `search_files_util` and `logger`.
  - Exception: `TestGetReferenceProjectPath` (`tests/test_reference_projects_mcp_tools.py:633-686`) stays
    unchanged in this step. It tests `server_reference_tools.get_reference_project_path`, which still
    exists, so its `server_reference_tools.ensure_available` patches must keep pointing there. Step 8 converts it.
  - The caplog logger name becomes `mcp_workspace.toolset.reference`.
  - Writes to `server_module._reference_projects` / `_read_max_lines` become
    `make_tools(reference_projects={...}, read_max_lines=...)`.
  - Delete `test_set_reference_read_max_lines_round_trip` (setter no longer exists).
  - The "cut at the limit" test becomes `make_tools(read_max_lines=3, reference_projects=...)`, with an unchanged assertion.

## WHAT

```python
async def reference_project_path(ctx: WorkspaceContext, name: str) -> Path:
    """Resolve a reference project name to its local path, ensuring availability."""

def reference_repo_url(ctx: WorkspaceContext, name: str) -> str:
    """Resolve a reference project name to its configured URL; never clones."""

def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    @log_function_call
    def get_reference_projects() -> dict[str, Any]: ...                       # sync
    @log_function_call
    async def read_reference_file(reference_name: ..., file_path: ..., start_line: ... = None,
                                  end_line: ... = None, with_line_numbers: ... = None) -> str: ...
    @log_function_call
    async def list_reference_directory(reference_name: ...) -> list[str]: ...
    @log_function_call
    async def search_reference_files(reference_name: ..., glob: ... = None, pattern: ... = None,
                                     context_lines: ... = 0, max_results: ... = 50,
                                     max_result_lines: ... = 200) -> dict[str, Any]: ...
    for fn in (get_reference_projects, read_reference_file, list_reference_directory, search_reference_files):
        sink.add(tool_spec(fn, group="workspace.reference", read_only=True))
```

## HOW

- Module-level imports, so tests can patch them:
  - `ensure_available` from `mcp_workspace.reference_projects`;
  - `read_file_util`, `list_files_util` and `search_files_util` (aliases as before);
  - `check_path_not_gitignored`;
  - `scrub_credentials`.
- Bodies are copied unchanged, except:
  - `_reference_projects` becomes `ctx.reference_projects`;
  - `_read_max_lines` becomes `ctx.read_max_lines`;
  - `get_reference_project_path(name)` becomes `await reference_project_path(ctx, name)`.
- `reference_project_path` / `reference_repo_url` keep today's error messages verbatim.
- `Args:` text goes into `Field` descriptions; tool signatures stay identical (snapshot).
- Write the new test first, in `tests/toolset/test_toolset.py`:
  - The four specs have `group == "workspace.reference"` and `read_only is True`.
  - `get_reference_projects` is sync; the other three are coroutine functions.

## ALGORITHM

```
async def reference_project_path(ctx, name):
    if name not in ctx.reference_projects: raise ValueError(f"Reference project '{name}' not found")
    project = ctx.reference_projects[name]
    await ensure_available(project)
    return project.path
```

## DATA

13 specs from `tool_specs`; 31 tools on the server.

## Checks

Snapshot green; all checks pass, including lint-imports with the reduced ignore list.
One commit: `refactor(toolset): move workspace.reference tools into toolset`.
