# Step 11 — Move group `workspace.checks`; remove the legacy machinery

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_11.md`.
> Move `check_file_size`, `check_branch_status` and `get_base_branch` into `toolset/checks.py`.
> `server.py` then has no tools and no module-level tool state: remove `_legacy_tool`,
> `_LEGACY_TOOLS`, `_configure_legacy`, all remaining globals and setters, and the unused imports.
> Adapt the tests first, then move the code. Run all checks, format, commit.

## WHERE

- `src/mcp_workspace/toolset/checks.py` (new)
- `src/mcp_workspace/toolset/__init__.py` (append `checks.register`; `_GROUPS` now has all 9 register functions)
- `src/mcp_workspace/server.py`:
  - Ends up containing only `_INSTRUCTIONS`, `FastMCPSink`, `create_server` and `run_server`.
  - Delete the legacy decorator, the legacy list and `_configure_legacy`, plus `_project_dir`,
    `set_project_dir`, `_file_size_limit`, `set_file_size_limit`, `_fail_on_reviews` and
    `set_fail_on_reviews`.
- `.importlinter`: update the `mcp_library_isolation` comment to "only server.py".
  The ignore list is already `server` only (step 7).
- `tach.toml`: `server` `depends_on` keeps only `mcp_workspace.toolset`, `mcp_workspace.file_tools`
  (`DEFAULT_READ_MAX_LINES` in `run_server`), `mcp_workspace.reference_projects` (type of
  `run_server`'s argument), `mcp_coder_utils.log_utils` and `mcp_coder_utils.tool_spec`.
  Drop whatever tach reports as unused.
- `.large-files-allowlist`: remove `src/mcp_workspace/server.py` and its comment.
- Tests:
  - `tests/test_server_file_size.py`:
    - patches of `mcp_workspace.server.check_file_sizes` / `render_output` / `render_allowlisted`
      become `mcp_workspace.toolset.checks.*`;
    - `set_file_size_limit(750)` becomes `make_tools(file_size_limit=750)`;
    - the `_reset_globals` fixtures are deleted;
    - line 100 (asserts against `server._project_dir`) asserts against the `project_dir` passed to `make_tools`.
  - `tests/test_server_fail_on_reviews.py`: tool tests use `make_tools(fail_on_reviews=...)`.
    Delete `TestSetFailOnReviews` (listed exception).
  - `tests/test_server_get_base_branch.py`: `get_base_branch` via `tools`.
  - `tests/test_server.py`:
    - `check_branch_status` tests via `tools`;
    - delete the `_project_dir is None` test for `check_branch_status` (lines 551–561);
    - the remaining `setup_server` fixture / `set_project_dir` / `_check_not_gitignored` imports go.
  - `tests/test_path_separator_invariant.py`: `check_file_size` via `tools`; its `server._project_dir`
    save/restore fixture becomes `make_tools(tmp_path)`.
  - Every other remaining `setup_server` autouse fixture in tests becomes unnecessary; delete it.
  - Search `tests/` for `mcp_workspace.server.` and `set_project_dir`. Only `run_server`,
    `create_server`, `FastMCPSink`, `tool_specs` and `FastMCP.run` references may remain.
- `vulture_whitelist.py`:
  - Delete the `_reset_globals` / `restore_read_max_lines` / `setup_server` entries that are now unused.
  - For the tool-name entries ("registered in server.py"): delete them if vulture passes
    without them; otherwise reword the comments to "registered via toolset".

## WHAT

```python
def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    @log_function_call
    def check_file_size(max_lines: Annotated[int | None, Field(...)] = None,
                        show_allowlisted: Annotated[bool, Field(...)] = False) -> str: ...
    @log_function_call
    async def check_branch_status(max_log_lines: ... = 300, ci_timeout: ... = 300,
                                  pr_timeout: ... = 0, fail_on_reviews: Annotated[bool | None, Field(...)] = None) -> str: ...
    @log_function_call
    def get_base_branch() -> str: ...
    for fn in (check_file_size, check_branch_status, get_base_branch):
        sink.add(tool_spec(fn, group="workspace.checks", read_only=True))
```

`server.py` at the end:

```python
def create_server(project_dir: Path, **settings: Any) -> FastMCP:
    mcp = FastMCP("File System Service", instructions=_INSTRUCTIONS)
    sink = FastMCPSink(mcp)
    for spec in tool_specs(project_dir, **settings):
        sink.add(spec)
    return mcp
```

## HOW

- Module-level imports in `checks.py`: `check_file_sizes`, `load_allowlist`, `render_allowlisted`,
  `render_output` (patch targets), and `resolve_base_branch` from `_github_common`.
- `branch_status_polling`, `branch_queries` and `PullRequestManager` stay lazy, inside the tool bodies.
- `_file_size_limit` becomes `ctx.file_size_limit`, `_fail_on_reviews` becomes `ctx.fail_on_reviews`,
  and `_project_dir` becomes `ctx.project_dir`.
- Delete the guards and their `Raises:` sections.
- `run_server` keeps its name, signature and `@log_function_call`; its body is just
  `create_server(project_dir, reference_projects=..., ...).run()` (it already is, since step 2).
- Write the new test first, in `tests/toolset/test_toolset.py`:
  - The three specs have `group == "workspace.checks"` and `read_only is True`.
  - `check_branch_status` is a coroutine function.

## ALGORITHM

`check_file_size`, unchanged apart from `ctx`:

```
effective = max_lines if max_lines is not None else ctx.file_size_limit
if effective is None: effective = 600
allowlist = load_allowlist(ctx.project_dir / ".large-files-allowlist")
if show_allowlisted: return render_allowlisted(ctx.project_dir, effective, allowlist)
return render_output(check_file_sizes(ctx.project_dir, max_lines=effective, allowlist=allowlist), effective)
```

## DATA

31 specs from `tool_specs`; `create_server` registers exactly those 31.

## Checks

Snapshot green; all checks pass, including vulture, tach, lint-imports and deptry. Run
`check_file_size`: no file over 750 lines without an allowlist entry. If a toolset module is over
750 lines, write one line to `pr_info/.blocked.txt` and stop. One commit:
`refactor(server): move workspace.checks into toolset and drop module-level tool state`.
