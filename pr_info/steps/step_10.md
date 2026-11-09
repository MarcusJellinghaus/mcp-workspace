# Step 10 — Move the write `workspace.github` tools; delete `server_reference_tools.py`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_10.md`.
> Move the eight GitHub write tools into `toolset/github_write.py`, with their helpers taking `ctx`
> where they read settings. Move `_resolve_base_branch` into `_github_common.py`; the legacy
> `get_base_branch` still uses it. `server_reference_tools.py` becomes unused: delete it and its
> config entries. Adapt the tests first, then move the code. Run all checks, format, commit.

## WHERE

- `src/mcp_workspace/toolset/github_write.py` (new)
- `src/mcp_workspace/toolset/_github_common.py`: add `resolve_base_branch` (moved from `server._resolve_base_branch`, unchanged signature)
- `src/mcp_workspace/toolset/__init__.py` (append `github_write.register`)
- `src/mcp_workspace/server.py`:
  - Delete the 8 tools.
  - Delete `_STATUS_LABEL_PREFIX`, `_check_labels`, `_check_base_branch`, `_resolve_assignees`,
    `_normalize_newlines`, `_edit_change_lines`, `_resolve_body`, `_subissue_write`,
    `_issue_manager`, `_pr_manager`, `_check_not_gitignored`, `_resolve_base_branch`,
    `_enforce_base_branch_format` and `set_enforce_base_branch_format`.
  - Delete the `set_enforce_base_branch_format` / `set_reference_projects` calls in `_configure_legacy`.
  - `get_base_branch` imports `resolve_base_branch` from `_github_common`.
- `src/mcp_workspace/server_reference_tools.py`: **delete** (no remaining user)
- `.importlinter`: in the layers contract, replace `mcp_workspace.server_reference_tools` with nothing.
  `mcp_workspace.toolset` already sits between `server` and `checks`.
- `tach.toml`:
  - Remove the `server_reference_tools` module entry.
  - Remove it from the `depends_on` lists of `server` and `tests`.
- `pyproject.toml`: remove the `server_reference_tools.py` per-file ignore.
- Tests:
  - `tests/github_operations/test_github_write_tools_issues.py`
    - imports become the `tools` fixture;
    - line 282 `patch("mcp_workspace.server._enforce_base_branch_format", False)` becomes
      `make_tools(enforce_base_branch_format=False)`.
  - `test_github_write_tools_issue_edit.py`.
  - `test_github_write_tools_issue_edit_base_branch.py` (line 199, same as above).
  - `test_github_write_tools_body_file.py`: line 55 patch `mcp_workspace.server._issue_manager` becomes
    `mcp_workspace.toolset.github_write.issue_manager`.
  - `test_github_write_tools_labels_pr.py`: line 221 patch becomes `mcp_workspace.toolset.github_write.resolve_base_branch`.
  - `test_github_write_tools_reference.py`.
  - `test_github_write_tools_subissues.py`.
  - `test_github_pr_create_base.py`: `RESOLVE = "mcp_workspace.toolset.github_write.resolve_base_branch"`.
  - `tests/test_server.py`:
    - remove `_check_not_gitignored` from the `mcp_workspace.server` import (line 14), so collection
      still works once `server._check_not_gitignored` is deleted;
    - `test_check_not_gitignored_absolute_path_message_is_forward_slash` (373–384) calls
      `check_not_gitignored(ctx, ...)` from `mcp_workspace.toolset._context`, with
      `ctx = WorkspaceContext(gitignore_project, {}, None, None, False, True)`. Assertion unchanged.
  - `tests/test_server_get_base_branch.py`:
    - import the public `resolve_base_branch` from `mcp_workspace.toolset._github_common` (matching
      the name in WHERE above) instead of `_resolve_base_branch` from `server`, and rename the call
      sites in `TestResolveBaseBranch` to `resolve_base_branch(...)`;
    - the `get_base_branch` tool stays legacy until step 11;
    - the caplog logger name for `_resolve_base_branch` warnings becomes `mcp_workspace.toolset._github_common`.
  - `tests/github_operations/conftest.py`: `setup_server` now has no users. Delete it, plus its
    `pytestmark` users and the `vulture_whitelist.py` entries `setup_server` / `pytestmark` if they
    become unused. Delete the `server` / `set_project_dir` imports.
  - Delete `tests/test_server_reference_tools.py` (setter tests, a listed exception).
  - Delete the `TestSetEnforceBaseBranchFormat` setter test in `tests/test_server_enforce_base_branch_format.py`
    (listed exception). Its `run_server` tests were already rewritten in step 2.

## WHAT

```python
# github_write.py
_STATUS_LABEL_PREFIX = "status-"

def _check_labels(manager: Any, add: list[str], remove: list[str], reference_name: str | None = None) -> str | None: ...
def _check_base_branch(ctx: WorkspaceContext, body: str | None) -> str | None: ...     # reads ctx.enforce_base_branch_format
def _resolve_assignees(manager: Any, logins: list[str]) -> list[str]: ...
def _normalize_newlines(text: str | None) -> str: ...
def _edit_change_lines(issue: Any, title: ..., body: ..., state: ..., add_labels: ..., remove_labels: ..., assignees: list[str]) -> list[str]: ...
def _resolve_body(ctx: WorkspaceContext, body: str | None, body_file: str | None, conflict: bool) -> str | None: ...
def _subissue_write(ctx: WorkspaceContext, parent_number: int, child_number: int, remove: bool, reference_name: str | None) -> str: ...

def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    # github_issue_create, github_issue_edit, github_issue_comment, github_review_comment_reply,
    # github_review_thread_resolve, github_subissue_add, github_subissue_remove, github_pr_create
    for fn in (...):
        sink.add(tool_spec(fn, group="workspace.github", read_only=False))
```

## HOW

- The helpers are copied unchanged, except:
  - `_project_dir` becomes `ctx.project_dir`;
  - `_enforce_base_branch_format` becomes `ctx.enforce_base_branch_format`;
  - `_issue_manager(r)` becomes `issue_manager(ctx, r)`;
  - `_check_not_gitignored(p)` becomes `check_not_gitignored(ctx, p)`.
- `_resolve_body` drops its `if _project_dir is None: raise ValueError(...)` guard, and the matching
  "the project directory is unset" wording in its `Raises:` (issue requirement).
- `issue_manager`, `pr_manager`, `ref_suffix`, `repo_access_error`, `api_error`, `tool_error` and
  `resolve_base_branch` are imported as module-level names from `_github_common`, so they are
  patchable as `mcp_workspace.toolset.github_write.<name>`.
- All PyGithub / GitPython imports stay inside function bodies (lazy).
- Write the new test first, in `tests/toolset/test_toolset.py`: the eight specs have `group == "workspace.github"` and `read_only is False`.

## ALGORITHM

`_check_base_branch`, unchanged apart from `ctx`:

```
if not ctx.enforce_base_branch_format: return None
from mcp_workspace.github_operations.issues.base import MalformedBaseBranchError, format_malformed_base_branch, parse_base_branch
try: parse_base_branch(body or "")
except MalformedBaseBranchError as exc: return f"Error: {format_malformed_base_branch(exc)}"
return None
```

## DATA

28 specs from `tool_specs`; 31 tools on the server (28 specs + 3 legacy checks tools).

## Checks

Snapshot green; all checks pass, including lint-imports (layers without `server_reference_tools`)
and tach. One commit: `refactor(toolset): move workspace.github write tools into toolset`.
