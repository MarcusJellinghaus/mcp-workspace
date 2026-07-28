# Step 1 — Rewrite the 7 docstring summary lines

**Commit:** 1 (docstring first-line rewrites in the two server files + verification passing)

> Prerequisite reading: `pr_info/steps/summary.md` (goal, rationale, verbatim strings).

## WHERE

- `src/mcp_workspace/server.py`
- `src/mcp_workspace/server_reference_tools.py`

## WHAT

Change **only the first line** of each of the following docstrings. Signatures, decorators,
`Args` / `Returns` / `Raises`, and all body paragraphs stay untouched.

### `src/mcp_workspace/server.py`

| Tool (approx line) | Old first line | New first line |
|---|---|---|
| `read_file` (203) | `Read the contents of a file.` | `Read a file, or a line slice via start_line/end_line.` |
| `save_file` (246) | `Write content to a file.` | `Write a file, creating parent directories as needed.` |
| `delete_directory` (369) | `Delete a directory from the filesystem.` | `Delete a directory (empty by default; recursive=True for non-empty).` |
| `move_file` (413) | `Move or rename a file or directory within the project.` | `Move or rename a file or directory (git-aware, preserves history).` |
| `edit_file` (479) | `Make a selective edit to a file using exact string matching.` | `Edit a file by exact string match; replace_all for multiple matches.` |
| `git` (528) | `Run a read-only git command.` | `Run a read-only git command on the workspace or a reference project.` |

### `src/mcp_workspace/server_reference_tools.py`

| Tool (approx line) | Old first line | New first line |
|---|---|---|
| `read_reference_file` (107) | `Read the contents of a file from a reference project.` | `Read a reference-project file, or a line slice via start_line/end_line.` |

## HOW

- Use exact-string edits on the docstring first line only. The `save_file` and
  `delete_directory` docstrings have a descriptive body paragraph below the summary that now
  slightly overlaps the new first line — **leave those paragraphs as-is** (touching them is
  out of scope; the overlap is harmless).
- These docstrings feed the auto-generated MCP tool schemas via the `@mcp.tool()` wrapper —
  no re-registration or code change needed; the new text propagates automatically.

## ALGORITHM

None — no logic. Pure text substitution:

```
for each (file, old_first_line, new_first_line) in the 7 rows above:
    locate the docstring opening line by tool name
    replace old_first_line with new_first_line (first line only)
    leave Args/Returns/Raises and body paragraphs unchanged
```

## DATA

No data structures, return values, or signatures change. Tool behavior is identical; only the
schema `description` strings differ.

## TDD note

Not applicable — there is no behavior to test and the issue verified no test pins these
strings. Verification is: (1) grep the test suite for the old summary strings to confirm none
are asserted, (2) run the standard quality gate.

## Verification (must pass before committing)

1. Search tests for the old strings (expect zero hits that pin docstring text):
   `read the contents of a file`, `Write content to a file`,
   `Delete a directory from the filesystem`, `within the project`,
   `Make a selective edit`, `Run a read-only git command`.
2. `mcp__mcp-tools-py__run_pylint_check`
3. `mcp__mcp-tools-py__run_pytest_check` with `extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]`
4. `mcp__mcp-tools-py__run_mypy_check`
5. `./tools/format_all.sh`, review diff is docstring-only, then commit.

## Suggested commit message

```
Surface Args-only capabilities in 7 tool summary lines

Rewrite the first docstring line of read_file, save_file, delete_directory,
move_file, edit_file, git, and read_reference_file so selection-relevant
capabilities (line slicing, reference-project targeting, recursive delete,
git-aware move, replace_all) are visible in the auto-generated tool schema.
Docstring-only; no logic change.
```
