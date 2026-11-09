# Step 3 — Move group `workspace.read` (`read_file`, `list_directory`, `search_files`)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md`.
> Move the three read tools from `server.py` into `toolset/read.py` as closures over
> `WorkspaceContext`, with parameter text moved from `Args:` into `Field` descriptions.
> First adapt the tests (setup / imports / patch targets only) and add the new spec test, then
> move the code. Delete what the move leaves unused. Run all checks, format, commit.

## WHERE

- `src/mcp_workspace/toolset/read.py` (new)
- `src/mcp_workspace/toolset/__init__.py` (append `read.register` to `_GROUPS`)
- `src/mcp_workspace/server.py` (delete the three tools, `_read_max_lines`, `set_read_max_lines`
  and its call in `_configure_legacy`)
- `pyproject.toml` (add `pydantic` to `[project] dependencies`; `toolset` now imports `Field`)
- Tests, adapting only the parts that use these three tools:
  - `tests/test_server.py`
    - read tests; `@patch("mcp_workspace.server.read_file_util")` becomes
      `mcp_workspace.toolset.read.read_file_util`;
    - line 420 `monkeypatch.setattr(server_module, "_read_max_lines", 3)` becomes `make_tools(read_max_lines=3)`.
  - `tests/test_server_list_directory.py`: patch targets become `mcp_workspace.toolset.read.list_files_util` / `.list_directory_tree`.
  - `tests/test_file_tool_path_rules.py`: entries for `read_file`, `list_directory` and `search_files`.
  - `tests/test_path_separator_invariant.py`: `list_directory`, `search_files`.
  - `tests/test_tool_descriptions.py`: the `search_files` case.

## WHAT

```python
def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.read tools bound to ctx."""

    @log_function_call
    def search_files(
        glob: Annotated[str | None, Field(description="File path pattern with gitignore/wildmatch semantics — ...")] = None,
        pattern: Annotated[str | None, Field(description="...")] = None,
        context_lines: Annotated[int, Field(description="...")] = 0,
        max_results: Annotated[int, Field(description="...")] = 50,
        max_result_lines: Annotated[int, Field(description="...")] = 200,
    ) -> dict[str, Any]: ...

    @log_function_call
    def list_directory(path: Annotated[str, Field(...)] = ".", dirs_only: Annotated[bool, Field(...)] = False) -> list[str]: ...

    @log_function_call
    def read_file(file_path: Annotated[str, Field(...)], start_line: ... = None,
                  end_line: ... = None, with_line_numbers: ... = None) -> str: ...

    for fn in (read_file, list_directory, search_files):
        sink.add(tool_spec(fn, group="workspace.read", read_only=True))
```

## HOW

### Code move

- Module-level imports in `read.py` are the names that tests patch:
  - `from mcp_workspace.file_tools import list_directory_tree, normalize_path`
  - `from mcp_workspace.file_tools import list_files as list_files_util`
  - `from mcp_workspace.file_tools import read_file as read_file_util`
  - `from mcp_workspace.file_tools import search_files as search_files_util`
- Bodies are copied unchanged, except:
  - `_project_dir` becomes `ctx.project_dir`;
  - `_read_max_lines` becomes `ctx.read_max_lines`;
  - `_check_not_gitignored(p)` becomes `check_not_gitignored(ctx, p)`;
  - the `if _project_dir is None: raise ...` guards are deleted.
- Docstrings:
  - Move each `Args:` entry verbatim (joined into one line of prose) into that parameter's `Field(description=...)`.
  - Delete the `Args:` section.
  - Delete "or the project directory has not been set" from `Raises:`. Keep any other Raises text.
- Keep the parameter types, defaults and order identical; the snapshot test enforces this.
- `logger = logging.getLogger(__name__)` in `read.py`.
- `server.py` still needs `_check_not_gitignored` for the legacy write/delete/move tools, so keep it.

### Tests

- Write the new test first, in `tests/toolset/test_toolset.py`. Step 12 extends this file.
  - `tool_specs(tmp_path)` contains `read_file`, `list_directory` and `search_files`.
  - Each has `group == "workspace.read"` and `read_only is True`.
- `tests/test_tool_descriptions.py`, `search_files` case:
  - The text checked is `spec.description` + the `glob` field description from
    `spec.args_model.model_json_schema()["properties"]["glob"]["description"]`, lowercased.
  - `glob_note` remains in the `Returns:` docstring.
  - Phrases unchanged. Keep the `search_reference_files` case on the old docstring until step 7.
- Test functions get the `tools` / `make_tools` fixture and call `tools["read_file"](...)`.
- In module-level case tables, these three entries become `lambda t, p: t["read_file"](p)`-style
  callables. The remaining legacy entries keep their current form until their step.
- Assertions are unchanged.

### Ruff

Fix any D/DOC finding the move causes, not by adding blanket ignores. D417 does not fire without an `Args:` section.

## ALGORITHM

No new logic; same bodies, bound to `ctx`.

## DATA

`tool_specs(...)` now returns 3 specs. `create_server` registers 3 specs + 24 legacy tools + 4 reference tools = 31.

## Checks

Snapshot green; all checks pass. If pylint flags `too-many-statements` / `too-many-locals` on
`register`, add `# pylint: disable=<msg>` on that `def` line. One commit:
`refactor(toolset): move workspace.read tools into toolset`.
