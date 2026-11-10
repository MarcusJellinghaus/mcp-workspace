# Library use (tool specs)

The same tools the MCP server exposes are available to non-MCP callers (e.g. a LangChain agent) as framework-neutral `ToolSpec`s, bound to a project directory you pass in:

```python
from pathlib import Path
from mcp_workspace.toolset import tool_specs

specs = tool_specs(Path("/path/to/project"), read_max_lines=2000)
tools = {s.name: s for s in specs}
tools["read_file"].fn("README.md")
```

`mcp_workspace.toolset` does not import `mcp`. The MCP server registers these same specs (`mcp_workspace.server.create_server`), so there is one tool list.

## Arguments

`project_dir` is required. The keyword arguments match the [command-line flags](../README.md#command-line-arguments):

| Argument | Default | CLI flag |
|---|---|---|
| `reference_projects` | `None` (no reference projects) | `--reference-project` |
| `read_max_lines` | `DEFAULT_READ_MAX_LINES` (2000); `None` or `0` = no limit | `--read-max-lines` |
| `file_size_limit` | `None` (built-in 600) | `--file-size-limit` |
| `fail_on_reviews` | `False` | `--fail-on-reviews` |
| `enforce_base_branch_format` | `True` | `--enforce-base-branch-format` |

## `ToolSpec` fields

- `name`: tool name, as in [Groups](#groups)
- `description`: tool description
- `fn`: the callable; sync or async
- `args_model`: pydantic model of the parameters, with their descriptions
- `group`: one of the groups below
- `read_only`: `True` for tools that only read (files, git, GitHub)

## Groups

| Group | Tools | `read_only` |
|---|---|---|
| `workspace.read` | `read_file`, `list_directory`, `search_files` | yes |
| `workspace.write` | `save_file`, `edit_file`, `append_file` | no |
| `workspace.delete` | `delete_this_file`, `delete_directory` | no |
| `workspace.move` | `move_file` | no |
| `workspace.git` | `git` | yes |
| `workspace.github` | `github_issue_view`, `github_issue_list`, `github_pr_view`, `github_search`, `github_label_list`, `github_subissue_list` | yes |
| `workspace.github` | `github_issue_create`, `github_issue_edit`, `github_issue_set_status`, `github_subissue_add`, `github_subissue_remove`, `github_issue_comment`, `github_review_comment_reply`, `github_review_thread_resolve`, `github_pr_create` | no |
| `workspace.checks` | `check_file_size`, `check_branch_status`, `get_base_branch` | yes |
| `workspace.reference` | `get_reference_projects`, `read_reference_file`, `list_reference_directory`, `search_reference_files` | yes |

## TLS and global state

- `tool_specs` has no global side effects. The `mcp-workspace` entry point activates the OS trust store (`truststore`) and labels [GitHub traffic log](../README.md#github-traffic-log) lines with its command name. The traffic log itself follows `config.toml` for library callers too, with an empty command field. Library callers that enable `workspace.github` or `workspace.checks` must set up TLS themselves. `workspace.read` and `workspace.write` need no network.
- Settings and file locks belong to one `tool_specs(...)` call; two calls never share them. Reference-project clone locks and clone-failure caches are process-global, keyed by reference name.
