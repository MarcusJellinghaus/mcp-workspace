# Step 1 — Document git-aware behavior in the surfaced `move_file` descriptions

**One commit:** the two doc edits + all quality checks passing.

See `pr_info/steps/summary.md` for full context, rationale, and out-of-scope notes.

## WHERE

- `src/mcp_workspace/server.py` — `move_file` tool function docstring (summary line, ~line 413).
- `README.md` — `move_file` row in the tools table (line 221).

**Do not** modify `src/mcp_workspace/file_tools/file_operations.py` (already correct,
out of scope), nor the `README.md:31` bullet, nor the `README.md:332-336` Features section.

## WHAT

No function signatures change. `move_file(source_path: str, destination_path: str) -> bool`
in `server.py` stays identical; only its docstring **summary line** changes.

Edit 1 — `server.py`, replace the docstring summary line so it reads:

```python
def move_file(source_path: str, destination_path: str) -> bool:
    """Move or rename a file or directory within the project. Git-aware: uses
    `git mv` for tracked files (preserving rename/history); falls back to a plain
    filesystem move for untracked files or non-git repos.

    Args:
        source_path: Source file/directory path (relative to project)
        destination_path: Destination path (relative to project)
    ...
    """
```

Keep the existing `Args:`, `Returns:`, and `Raises:` sections unchanged.

Edit 2 — `README.md:221`, replace the single table row (keep `| ... |` structure, one line):

```
| `move_file` | Moves or renames files/directories (git-aware: uses git mv for tracked files, else filesystem move) | "Rename config.js to settings.js" |
```

## HOW (integration points)

- No new imports, decorators, or wiring. `server.py` keeps `@mcp.tool()` and
  `@log_function_call` exactly as-is; only the docstring text under them changes.
- Use `mcp__mcp-workspace__edit_file` for both edits (exact-string replacement).
- Verify with the current line context first via `mcp__mcp-workspace__read_file`
  (line numbers may have shifted).

## ALGORITHM

Not applicable — no logic changes. Pure documentation wording.

## DATA

No return values or data structures change. `move_file` still returns `bool`.

## TDD note

Not applicable — documentation text only, no behavior to test-drive, and no existing
test asserts on the docstring wording. Do not add a brittle docstring-substring test
(KISS; low value, high maintenance). Correctness is confirmed by the quality checks below.

## Verification (must all pass before commit)

Run via MCP tools per CLAUDE.md:

```
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check   # extra_args: ["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]
mcp__mcp-tools-py__run_mypy_check
```

Then before commit: run `./tools/format_all.sh`, review `git diff` (should be docs-only),
stage, and commit.

## Commit message

```
Clarify move_file description: document git-aware behavior (#49)
```
