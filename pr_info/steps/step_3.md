# Step 3 — Single-path enforcement in the tools

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_3.md`), and issue #83 (Tool behaviour, Refused write, Invalid rules file).
> Implement step 3 only: tests first, then switch every single-path check from `check_not_gitignored` to `check_readable` / `check_writable`.
> Tree checks and listings come in later steps. Run pylint, pytest (`-n auto`) and mypy; all must pass. Format, then make exactly one commit.

## WHERE

- `src/mcp_workspace/toolset/_context.py`
- `src/mcp_workspace/toolset/read.py`, `write.py`, `delete.py`, `move.py`, `reference.py`
- `src/mcp_workspace/toolset/_github_write_helpers.py`, `github_write.py`
- `tests/test_server.py` (imports `check_not_gitignored`)
- New: `tests/test_file_access_tools.py`

## WHAT

```python
# toolset/_context.py — replaces check_not_gitignored (delete it)
def check_readable(ctx: WorkspaceContext, file_path: str) -> None: ...
def check_writable(ctx: WorkspaceContext, file_path: str) -> None: ...
```

## HOW

| Call site | New check |
|---|---|
| `read.py` `read_file` | `check_readable` |
| `read.py` `list_directory` | `check_path_not_gitignored(path, ctx.project_dir)` directly (unchanged behaviour until step 6) |
| `write.py` `save_file`, `append_file`, `edit_file` | `check_writable` |
| `delete.py` `delete_this_file`, `delete_directory` | `check_writable` |
| `move.py` source and destination (stay before the `try`) | `check_writable` |
| `_github_write_helpers.resolve_body` (body_file read) | `check_readable` |
| `_github_write_helpers.check_body_target` (`github_issue_view` body_file write) | `check_writable` |
| `reference.py` `read_reference_file` | `require_access(file_path, ref_path, FileAccess.READ_ONLY)` |

Docstrings / descriptions:
- `_BODY_FILE_RULES` (`github_write.py`): `"Same path rules as read_file: gitignored paths are refused unless .mcp-file-access exposes them."`
- `resolve_body` / `check_body_target` Raises: mention read-only paths (write target) and `.mcp-file-access` exposure.
- `delete_directory` tool Raises: add "read-only by .mcp-file-access".

## ALGORITHM

```
check_readable(ctx, p):  require_access(p, ctx.project_dir, FileAccess.READ_ONLY)
check_writable(ctx, p):  require_access(p, ctx.project_dir, FileAccess.READ_WRITE)
```

## DATA

No new return values; refusals are `ValueError` with the messages from step 2.

## Tests (`tests/test_file_access_tools.py`, write first)

Use `make_tools(root)` from `tests/conftest.py`. Fixture project: `.gitignore` with `*.log` and `.scratch/`, committed `plain.txt`, `.mcp.json`; ignored `app.log`; `.scratch/` folder.

- Matrix, parametrized: `save_file`, `append_file`, `edit_file`, `delete_this_file` × rule (none / `read-only` / `read-write`) × path (committed / ignored):
  none+committed → allowed; none+ignored → gitignore refusal; `read-only` → `No write access … (rule '<pattern>' in .mcp-file-access)`; `read-write` → allowed. Refused calls leave the file bytes unchanged.
- `read_file`: exposed ignored file readable (both levels); unexposed ignored file refused.
- `move_file`: read-only source refused; read-only destination refused; nothing moved.
- `delete_directory` on a directory path that is read-only by rule → refused.
- Rules file: `save_file(".mcp-file-access", …)` refused with `(built-in)`, both when absent (file not created) and present; `edit_file` / `delete_this_file` on it refused.
- Spellings: `save_file(".mcp.json.", …)` refused; `.MCP.json` refused (win32 only).
- `read-write /.git/` rule → `save_file(".git/config", …)` still refused.
- Invalid rules file (unknown level): `save_file("plain.txt", …)` refused with `.mcp-file-access is invalid: line 1: unknown level …`; `read_file("plain.txt")` works; `read_file` of a path exposed by an otherwise valid-looking rule is refused.
- body_file (build a `WorkspaceContext` directly): `resolve_body` reads an exposed ignored file; `check_body_target` refuses `.mcp.json` under `read-only /.mcp.json` and accepts `.scratch/body.md` under `read-write /.scratch/`.
- Reference project with its own rules file (fixture style of `tests/test_reference_path_rules.py`): `read_reference_file` reads an ignored file exposed `read-only`, and one exposed `read-write`.
- Update `tests/test_server.py`: `check_not_gitignored` → `check_readable` (same message assertion).
- `tests/test_file_tool_path_rules.py` and `tests/test_reference_path_rules.py` must pass unchanged.
