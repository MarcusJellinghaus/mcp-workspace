# Step 2 — `toolset` skeleton, `create_server`, `FastMCPSink`, test fixtures

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md`.
> Create the empty `toolset` factory and `WorkspaceContext`, and replace the module-level `mcp`
> with `create_server(...)`, which still registers the not-yet-moved tools. No tool moves yet.
> Tests first (fixtures, `create_server` tests), then the implementation. Run pylint,
> pytest (`-n auto`), mypy, ruff, lint-imports, tach, vulture, deptry, then format and commit.

## Precondition

`from mcp_coder_utils.tool_spec import ToolCollector, ToolSink, ToolSpec, tool_spec` must
import in the project environment. If it does not, write one line to
`pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/toolset/__init__.py` (new)
- `src/mcp_workspace/toolset/_context.py` (new)
- `src/mcp_workspace/server.py`
- `src/mcp_workspace/server_reference_tools.py` (unchanged API; `register(mcp)` now called from `create_server`)
- `.importlinter`, `tach.toml`
- `tests/conftest.py` (fixtures `make_tools`, `tools`)
- Tests that used the module-level `mcp`:
  - `tests/toolset/test_tool_schema_snapshot.py`
  - `tests/test_server_instructions.py`
  - `tests/test_tool_output_schema.py`
  - `tests/test_tool_refusals_mcp_layer.py`
- Tests that patch `mcp_workspace.server.mcp.run`:
  - `tests/test_server.py` (582–623)
  - `tests/test_server_file_size.py` (121–136)
  - `tests/test_server_fail_on_reviews.py` (40–55)
  - `tests/test_server_enforce_base_branch_format.py`

## WHAT

`toolset/_context.py`:

```python
@dataclass(frozen=True)
class WorkspaceContext:
    """Per-factory state shared by the tool closures of one tool_specs() call."""
    project_dir: Path
    reference_projects: dict[str, ReferenceProject]
    read_max_lines: int | None
    file_size_limit: int | None
    fail_on_reviews: bool
    enforce_base_branch_format: bool
    file_locks: dict[str, asyncio.Lock] = field(default_factory=dict)

def check_not_gitignored(ctx: WorkspaceContext, file_path: str) -> None:
    """Raise ValueError if file_path is excluded by .gitignore (security boundary)."""
    check_path_not_gitignored(file_path, ctx.project_dir)
```

`toolset/__init__.py`:

```python
def tool_specs(
    project_dir: Path,
    *,
    reference_projects: dict[str, ReferenceProject] | None = None,
    read_max_lines: int | None = DEFAULT_READ_MAX_LINES,
    file_size_limit: int | None = None,
    fail_on_reviews: bool = False,
    enforce_base_branch_format: bool = True,
) -> tuple[ToolSpec, ...]: ...

__all__ = ["tool_specs"]
```

`server.py`:

```python
_INSTRUCTIONS = "This server provides file operations ..."   # existing text, unchanged

class FastMCPSink:
    """ToolSink that registers each spec on a FastMCP server."""
    def __init__(self, mcp: FastMCP) -> None: ...
    def add(self, spec: ToolSpec) -> None:
        self._mcp.add_tool(spec.fn, name=spec.name, description=spec.description)

def create_server(project_dir: Path, **settings: Any) -> FastMCP: ...

_LEGACY_TOOLS: list[Callable[..., Any]] = []      # temporary, removed in step 11
def _legacy_tool(fn: F) -> F: ...                   # appends fn, returns it unchanged
def _configure_legacy(project_dir: Path, settings: dict[str, Any]) -> None: ...  # temporary

@log_function_call
def run_server(project_dir, reference_projects=None, file_size_limit=None,
               fail_on_reviews=False, enforce_base_branch_format=True,
               read_max_lines=DEFAULT_READ_MAX_LINES) -> None:   # signature unchanged
```

## HOW

- `server.py`:
  - Delete `mcp = FastMCP(...)` and the import-time `register_reference_tools(mcp)`.
  - On every tool, replace `@mcp.tool()` with `@_legacy_tool`, keeping `@log_function_call` below it.
- `create_server`, in this order:
  1. Build `FastMCP("File System Service", instructions=_INSTRUCTIONS)`.
  2. Add `tool_specs(project_dir, **settings)` through `FastMCPSink`.
  3. Call `_configure_legacy(project_dir, settings)`.
  4. Call `mcp.add_tool(fn)` for each fn in `_LEGACY_TOOLS`.
  5. Call `register_reference_tools(mcp)`.
- `_configure_legacy` calls the existing setters with `settings.get(key, <today's default>)`:
  - `set_project_dir`, `set_file_size_limit`, `set_read_max_lines`, `set_reference_read_max_lines`,
    `set_fail_on_reviews` and `set_enforce_base_branch_format`;
  - `set_reference_projects(settings.get("reference_projects") or {})`.

  Later steps delete the calls they make dead.
- `run_server` passes its arguments as keywords to `create_server(...)` and calls `.run()`.
- `tool_specs`:
  - Builds `WorkspaceContext(Path(project_dir), dict(reference_projects or {}), ...)` and a
    `ToolCollector`.
  - Loops over `_GROUPS: tuple[Callable[[ToolSink, WorkspaceContext], None], ...] = ()`, which is
    empty for now; later steps append each group's `register`.
  - Returns `tuple(dataclasses.replace(s, description=inspect.cleandoc(s.description)) for s in collector)`.
- `.importlinter` layers:
  - Insert `mcp_workspace.toolset` below `mcp_workspace.server_reference_tools` and above `mcp_workspace.checks`.
  - Leave `mcp_library_isolation` unchanged for now; step 7 updates it.
- `tach.toml`:
  - Add a layer `"toolset"` to `layers`, between `"protocol"` and `"tools"`.
  - Add a `[[modules]]` entry `mcp_workspace.toolset` in layer `toolset`, with `depends_on`:
    `mcp_workspace.file_tools`, `mcp_workspace.git_operations`, `mcp_workspace.github_operations`,
    `mcp_workspace.checks`, `mcp_workspace.reference_projects`, `mcp_workspace.config`,
    `mcp_workspace.utils`, `mcp_coder_utils.log_utils`, `mcp_coder_utils.tool_spec`.
    - `utils` is needed later for `scrub_credentials`; drop any dependency tach reports as unused.
  - Add `[[modules]] path = "mcp_coder_utils.tool_spec"` in layer `utilities` with `depends_on = []`.
  - Add `mcp_workspace.toolset` and `mcp_coder_utils.tool_spec` to `depends_on` for `server` and for `tests`.
- `tests/conftest.py`: add the `make_tools` / `tools` fixtures exactly as in the summary.
- Test adaptations (setup only):
  - `test_server_instructions.py`: `create_server(tmp_path).instructions`.
  - `test_tool_output_schema.py`: `create_server(tmp_path)` for both tests.
    - The second test drops its `server_reference_tools` monkeypatch, because `create_server`
      sets references to `{}` anyway.
  - `test_tool_refusals_mcp_layer.py`: the `workspace` fixture builds
    `create_server(tmp_path / "workspace", reference_projects={"ref": ...})` instead of
    monkeypatching globals; `_call` takes the server.
  - Snapshot test: `create_server(tmp_path).list_tools()`.
- The "run_server threads X" tests are rewritten now, per the issue's listed exceptions:
  - Patch `mcp_workspace.server.tool_specs` (return `()`) and `mcp_workspace.server.FastMCP.run`.
  - Assert that `tool_specs` was called with `project_dir` and the expected keyword (`file_size_limit`, `fail_on_reviews`,
    `enforce_base_branch_format`, `read_max_lines`, `reference_projects`), and that the defaults
    are today's defaults when the argument is omitted.
  - This replaces `test_server_file_size.py:121-136`, `test_server_fail_on_reviews.py:40-55`,
    `test_server_enforce_base_branch_format.py` (run_server part) and `test_server.py:582-623`
    (including the `restore_read_max_lines` fixture).
  - These tests stay valid unchanged through later steps.
- New tests in `tests/test_server.py` (TDD, written first):
  - `create_server(tmp_path)` returns a fresh `FastMCP` each call: two calls give two distinct objects.
  - Each `list_tools()` has the 31 names.
  - `FastMCPSink.add` registers a spec under `spec.name` with `spec.description`, checked on a tiny
    hand-made spec built with `tool_spec`.

## ALGORITHM

```
def tool_specs(project_dir, *, ...):
    ctx = WorkspaceContext(Path(project_dir), dict(reference_projects or {}), read_max_lines,
                           file_size_limit, fail_on_reviews, enforce_base_branch_format)
    collector = ToolCollector()
    for register in _GROUPS: register(collector, ctx)
    return tuple(replace(s, description=inspect.cleandoc(s.description)) for s in collector)
```

## DATA

- `tool_specs` returns `()` in this step.
- `create_server` returns a `FastMCP` that lists all 31 tools.

## Checks

The snapshot test is still green and all checks pass. One commit:
`refactor(server): build FastMCP per call via create_server and toolset factory`.
