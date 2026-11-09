# Step 14 — Documentation

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_14.md`.
> Document library use of the toolset and update the architecture docs and contract comments
> to the new structure. Docs only. Run all checks, format, commit.

## WHERE

- `README.md`: new section "Library use (tool specs)"
- `docs/ARCHITECTURE.md`
- `CONTRIBUTING.md` (project tree around line 120)
- `tests/README.md` (test layout: `tests/toolset/`, `make_tools` / `tools` fixtures)
- `docs/release-notes.md`
- `.importlinter` / `tach.toml` comment blocks, if still describing `server_reference_tools` or "main.py and server.py"

## WHAT

README section contents:

- **Example call:**
  ```python
  from pathlib import Path
  from mcp_workspace.toolset import tool_specs

  specs = tool_specs(Path("/path/to/project"), read_max_lines=2000)
  tools = {s.name: s for s in specs}
  tools["read_file"].fn("README.md")
  ```
- **Arguments:** the keyword arguments and their defaults (`reference_projects=None`,
  `read_max_lines=DEFAULT_READ_MAX_LINES`, `file_size_limit=None`, `fail_on_reviews=False`,
  `enforce_base_branch_format=True`). They match the CLI flags.
- **`ToolSpec` fields:** `name`, `description`, `fn` (sync or async), `args_model`, `group`, `read_only`.
- **Groups:** the groups table from the summary.
- **TLS note:** the MCP entry point activates the OS trust store (truststore) and traffic
  logging. Library callers that enable `workspace.github` or `workspace.checks` must set up TLS
  themselves. The factory has no global side effects. `workspace.read` / `workspace.write` need no network.
- **Per-call state:** settings and file locks are per factory call. Reference-project clone locks and
  failure caches are process-global, keyed by reference name.

## HOW

- `docs/ARCHITECTURE.md`:
  - Layer diagram: `main → server → toolset → checks / file_tools / github_operations / … `.
  - `server.py` is now "builds a FastMCP per call from `tool_specs`".
  - The `mcp` row in the library table becomes `server.py` only. This fixes the wrong claim that
    `main.py` imports `mcp`.
  - Line 77 ("`server.py` imports `github_operations` …") now describes `toolset/` and the lazy imports.
- `CONTRIBUTING.md`: add `toolset/` to the tree and drop `server_reference_tools.py`.
- `docs/release-notes.md`: one entry. Covers the new `mcp_workspace.toolset.tool_specs`, the new
  `server.create_server`, and the MCP tool list being unchanged. Parameter descriptions moved into
  the JSON schema, so the tool description texts no longer contain `Args:` sections.
- Follow each file's existing style and length. No other changes.

## ALGORITHM

None.

## DATA

None.

## Checks

All checks pass (docs only; pytest unchanged). One commit:
`docs: document toolset library use and new server structure`.
