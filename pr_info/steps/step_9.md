# Step 9 — Move the read-only `workspace.github` tools + shared GitHub helpers

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_9.md`.
> Move the six read-only GitHub tools into `toolset/github_read.py`, and the helpers they need into
> `toolset/_github_common.py`. Legacy write tools in `server.py` import the ctx-free helpers
> from `_github_common` instead of keeping copies. Keep every PyGithub import lazy.
> Adapt the tests first, then move the code. Run all checks, format, commit.

## WHERE

- `src/mcp_workspace/toolset/_github_common.py` (new)
- `src/mcp_workspace/toolset/github_read.py` (new)
- `src/mcp_workspace/toolset/__init__.py` (append `github_read.register`)
- `src/mcp_workspace/server.py`:
  - Delete `github_issue_view`, `github_issue_list`, `github_pr_view`, `github_search`,
    `github_label_list` and `github_subissue_list`.
  - Delete `_linked_branches`, `_repo_full_name` and `_allowlist_for`.
  - Delete the local definitions of `_ref_suffix`, `_repo_access_error`, `_api_error` and `_tool_error`;
    import them from `_github_common` (public names, see WHAT).
  - Keep `_issue_manager` / `_pr_manager` (ctx-free copies still used by legacy write tools until step 10).
- Tests, adapting the parts for these six tools:
  - `tests/github_operations/test_github_read_tools_issues.py`
  - `test_github_read_tools_pr_search.py`
  - `test_github_read_tools_reference.py`
  - `test_github_search_tool.py`
  - the `github_label_list` tests in `test_github_write_tools_labels_pr.py`
  - the `github_subissue_list` tests in `test_github_write_tools_subissues.py`

## WHAT

`_github_common.py`, with signatures and docstrings copied from today's `server.py` helpers:

```python
def ref_suffix(reference_name: str | None) -> str: ...
def issue_manager(ctx: WorkspaceContext, reference_name: str | None) -> "IssueManager": ...
def pr_manager(ctx: WorkspaceContext, reference_name: str | None) -> "PullRequestManager": ...
def linked_branches(ctx: WorkspaceContext, number: int, reference_name: str | None) -> list[str] | None: ...
def repo_access_error(manager: "IssueManager") -> str: ...
def repo_full_name(manager: "IssueManager") -> str | None: ...
def allowlist_for(associations: Iterable[str | None]) -> frozenset[str]: ...
def api_error(exc: Exception, reference_name: str | None) -> str: ...
def tool_error(e: Exception) -> str: ...
```

`github_read.py`:

```python
def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    # github_issue_view, github_issue_list, github_pr_view, github_search,
    # github_label_list, github_subissue_list — signatures identical to today
    for fn in (...):
        sink.add(tool_spec(fn, group="workspace.github", read_only=True))
```

## HOW

- `issue_manager` / `pr_manager` / `linked_branches`:
  - Workspace repo: `IssueManager(project_dir=ctx.project_dir)` (and likewise for the others).
  - Reference project: `repo_url=reference_repo_url(ctx, name)`, imported from `toolset.reference`.
- `IssueManager`, `PullRequestManager` and the `trust` / `config` imports stay **inside** the function
  bodies (lazy). Type names are referenced only under `TYPE_CHECKING`.
- Annotations in tool signatures use builtins only. Manager types appear only in helper return
  annotations, as strings under `TYPE_CHECKING`.
- `github_read.py` imports the helpers as module-level names, e.g.
  `from mcp_workspace.toolset._github_common import issue_manager, tool_error, ...`.
  Tests that need to patch them use `mcp_workspace.toolset.github_read.<name>`.
- `allowlist_for` keeps `from mcp_workspace import config` / `config.get_trusted_commenters()`, so the
  autouse conftest patch on `mcp_workspace.config` still applies.
- `pr_manager` is created here for completeness, but nothing reads it until step 10. If vulture
  flags it, move its creation to step 10.
- Tests:
  - `set_reference_projects(...)` fixtures for these tools become `make_tools(reference_projects={...})`.
  - `_TOOL_CASES` tables hold tool names instead of function objects.
  - The live search test re-points by calling `make_tools(<repo root>)` instead of `set_project_dir`.
  - Legacy write-tool tests in the same files keep `setup_server` / `set_reference_projects` until step 10.
- Write the new test first, in `tests/toolset/test_toolset.py`: the six specs have `group == "workspace.github"` and `read_only is True`.

## ALGORITHM

```
def issue_manager(ctx, reference_name):
    from mcp_workspace.github_operations.issues import IssueManager      # lazy
    if reference_name is None: return IssueManager(project_dir=ctx.project_dir)
    return IssueManager(repo_url=reference_repo_url(ctx, reference_name))
```

## DATA

20 specs from `tool_specs`; 31 tools on the server.

## Checks

Snapshot green; all checks pass; `test_startup_performance.py` green. One commit:
`refactor(toolset): move read-only workspace.github tools into toolset`.
