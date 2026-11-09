# Summary — Issue #378: export workspace tools as `ToolSpec`s from a `toolset` factory

Part of MarcusJellinghaus/agent-workbench#13 (step 3a). Builds on
`mcp_coder_utils.tool_spec` (`ToolSpec`, `tool_spec`, `ToolSink`, `ToolCollector`)
and `file_tools.DEFAULT_READ_MAX_LINES`. The issue text is the specification; this
file is the plan for implementing it.

## Goal

```
tool_specs(project_dir, ...) -> tuple[ToolSpec, ...]
   ├─ MCP server:      create_server() registers the specs with FastMCP
   └─ agent-workbench: wraps the specs as LangChain tools
```

The same 31 tools, with the same names, checks and parameter schemas, are available to a non-MCP
consumer, bound to a project directory the consumer passes in. The MCP server
registers those same specs, so there is one tool list.

## Architectural / design changes

| Before | After |
|---|---|
| 27 tools defined at module level in `server.py`, 4 in `server_reference_tools.py`, registered on a module-level `mcp` at import time | 31 tools defined as closures inside `register(sink, ctx)` of one module per group in `mcp_workspace/toolset/` |
| Settings in module globals (`_project_dir`, `_read_max_lines`, `_file_locks`, …) set via `set_*` setters | Settings in a frozen `WorkspaceContext` built once per `tool_specs(...)` call; two factories never share state |
| `run_server` calls setters, then `mcp.run()` | `run_server(...)` = `create_server(...).run()`; `create_server` builds a fresh `FastMCP` and adds each spec via `FastMCPSink` |
| Parameter text in Google-style `Args:` sections | Parameter text in `Annotated[..., Field(description=...)]`; `Args:` removed from tool docstrings (one source per parameter) |
| `if _project_dir is None: raise ValueError(...)` guards | Dropped — `project_dir` is a required factory argument |
| `mcp` importable by `server` and `server_reference_tools` | Only `mcp_workspace.server` imports `mcp`; `toolset` is MCP-free |

Key design points:

- **Package `mcp_workspace/toolset/`.** `__init__.py` holds `tool_specs(...)`. It builds the
  context, calls each group's `register(collector, ctx)`, and returns
  the specs with descriptions passed through `inspect.cleandoc`. That one call
  covers every tool, because closures carry extra docstring indentation on 3.11/3.12.
- **`toolset/_context.py`** holds `WorkspaceContext` and `check_not_gitignored(ctx, path)`.
  It is a separate module because group modules import it while `__init__` imports the group
  modules (a cycle otherwise).
- **Defaults live once**, in the `tool_specs` signature. `WorkspaceContext` fields have
  no defaults except `file_locks`.
- **Tool functions are closures** over `ctx`. Their parameter annotations must use
  builtins / module-level names only (`tool_spec` uses `inspect.signature(fn, eval_str=True)`).
  `log_function_call` uses `functools.wraps`, so the real signature and
  `iscoroutinefunction` stay visible.
- **Lazy imports stay.** GitPython / PyGithub / markdown-it are imported only inside tool bodies
  or helpers when a git/GitHub tool runs, never when the tools are built.
- **Patch targets** in tests are module-level names looked up at call time in the
  module that *calls* them, e.g. `mcp_workspace.toolset.read.read_file_util` or
  `mcp_workspace.toolset.reference.ensure_available`.
- **The MCP tool list stays identical.** No `readOnlyHint`. The snapshot test from step 1 pins
  every tool's input schema (names, types, defaults, required; not `description`/`title`).
- **Library TLS is documented, not handled.** `main.py` keeps truststore and traffic logging. The
  factory has no global side effects.
- **`reference_projects._project_locks` / `_clone_failure_cache`** stay process-global (out of scope).

### Groups and `read_only`

| Group | Module | Tools | read_only |
|---|---|---|---|
| `workspace.read` | `read.py` | `read_file`, `list_directory`, `search_files` | yes |
| `workspace.write` | `write.py` | `save_file`, `edit_file`, `append_file` | no |
| `workspace.delete` | `delete.py` | `delete_this_file`, `delete_directory` | no |
| `workspace.move` | `move.py` | `move_file` | no |
| `workspace.git` | `git.py` | `git` | yes |
| `workspace.github` | `github_read.py` | `github_issue_view`, `github_issue_list`, `github_pr_view`, `github_search`, `github_label_list`, `github_subissue_list` | yes |
| `workspace.github` | `github_write.py` | `github_issue_create`, `github_issue_edit`, `github_issue_comment`, `github_review_comment_reply`, `github_review_thread_resolve`, `github_subissue_add`, `github_subissue_remove`, `github_pr_create` | no |
| `workspace.checks` | `checks.py` | `check_file_size`, `check_branch_status`, `get_base_branch` | yes |
| `workspace.reference` | `reference.py` | `get_reference_projects`, `read_reference_file`, `list_reference_directory`, `search_reference_files` | yes |

The GitHub group is split over two modules plus `_github_common.py` (shared helpers) so that
no file exceeds the 750-line limit. Both modules use group `workspace.github`.

## Migration strategy (how steps stay green)

- **Step 1** pins the current schemas in a snapshot.
- **Step 2** introduces the factory with no groups, plus `create_server` and `FastMCPSink`. The
  module-level `mcp` goes away. Not-yet-moved tools are marked `@_legacy_tool` (a one-line swap for
  `@mcp.tool()`) and added by `create_server`. `create_server` also calls the old setters
  (`_configure_legacy`) so legacy tools see the same settings as the moved ones.
- **Steps 3–11** move one group each. **Each step deletes what its move leaves unused**:
  globals, setters, `server.py` helpers, setter calls in `_configure_legacy`, and the tests of
  deleted setters. Leaving dead code would fail vulture, and import-linter fails on an
  unmatched `ignore_imports` entry. A ctx-free helper that legacy code still needs is imported
  from `toolset` instead of being duplicated (`server` may depend on `toolset`).
- **Step 11** moves the last group and removes the legacy machinery (`_legacy_tool`,
  `_configure_legacy`, `_project_dir`, `set_project_dir`).
- **Step 12** adds the acceptance tests; **step 13** the subprocess import tests; **step 14** docs.

The snapshot test runs in every step. It is the safety net for "schemas unchanged".

## Shared test fixture

`tests/conftest.py` gains:

```python
ToolMap = dict[str, Callable[..., Any]]

@pytest.fixture
def make_tools(project_dir: Path) -> Callable[..., ToolMap]:
    """Build tools via tool_specs; returns {name: fn}."""
    def _make(root: Path | None = None, **settings: Any) -> ToolMap:
        return {s.name: s.fn for s in tool_specs(root or project_dir, **settings)}
    return _make

@pytest.fixture
def tools(make_tools: Callable[..., ToolMap]) -> ToolMap:
    return make_tools()
```

Tests replace `from mcp_workspace.server import read_file` and `read_file(...)` with
`tools["read_file"](...)`. Tests that set a global use `make_tools(read_max_lines=3)`,
`make_tools(reference_projects={...})`, and so on. Module-level case tables that held
function objects hold tool names instead.

## Files and modules

### Created

```
src/mcp_workspace/toolset/__init__.py        tool_specs(...)
src/mcp_workspace/toolset/_context.py        WorkspaceContext, check_not_gitignored
src/mcp_workspace/toolset/read.py            workspace.read
src/mcp_workspace/toolset/write.py           workspace.write
src/mcp_workspace/toolset/delete.py          workspace.delete
src/mcp_workspace/toolset/move.py            workspace.move
src/mcp_workspace/toolset/reference.py       workspace.reference (+ reference_project_path / reference_repo_url)
src/mcp_workspace/toolset/git.py             workspace.git
src/mcp_workspace/toolset/_github_common.py  GitHub helpers shared by read/write/checks
src/mcp_workspace/toolset/github_read.py     workspace.github (read-only)
src/mcp_workspace/toolset/github_write.py    workspace.github (write)
src/mcp_workspace/toolset/checks.py          workspace.checks
tests/toolset/__init__.py
tests/toolset/tool_schema_snapshot.json      captured in step 1
tests/toolset/test_tool_schema_snapshot.py
tests/toolset/test_toolset.py                acceptance tests (step 12)
tests/toolset/test_toolset_imports.py        subprocess sys.modules tests (step 13)
```

### Modified

```
src/mcp_workspace/server.py                  create_server, FastMCPSink, run_server; all tools and globals removed
pyproject.toml                               pydantic dependency; ruff per-file ignore moves to toolset/reference.py
.importlinter                                mcp isolation = server only; layers: toolset replaces server_reference_tools
tach.toml                                    toolset layer/module, mcp_coder_utils.tool_spec module, server/tests depends_on
.large-files-allowlist                       drop src/mcp_workspace/server.py
vulture_whitelist.py                         tool-name entries/comments
tests/conftest.py                            make_tools / tools fixtures
tests/** (existing)                          setup / imports / patch targets (see each step)
README.md, docs/ARCHITECTURE.md, CONTRIBUTING.md, tests/README.md, docs/release-notes.md
```

### Deleted

```
src/mcp_workspace/server_reference_tools.py  (step 10)
tests/test_server_reference_tools.py         (step 10; setter tests)
```

## Steps

| Step | Content |
|---|---|
| 1 | Schema snapshot test (before any tool moves) |
| 2 | `toolset` skeleton, `create_server` + `FastMCPSink`, module `mcp` removed, fixtures, contracts |
| 3 | `workspace.read` |
| 4 | `workspace.write` |
| 5 | `workspace.delete` |
| 6 | `workspace.move` |
| 7 | `workspace.reference` |
| 8 | `workspace.git` |
| 9 | `workspace.github` read tools + `_github_common.py` |
| 10 | `workspace.github` write tools; `server_reference_tools.py` deleted |
| 11 | `workspace.checks`; legacy machinery removed |
| 12 | Acceptance tests (groups, isolation, defaults, `args_model`) |
| 13 | Subprocess import tests (no `mcp`; lazy git/github) |
| 14 | Docs |

## Checks per step

Every step ends with all of the following passing:
- pylint, pytest (`-n auto`), mypy, ruff
- `run_lint_imports_check`, `run_tach_check`, `run_vulture_check`, `run_deptry_check`
- `run_format_code` before the commit

One commit per step.
