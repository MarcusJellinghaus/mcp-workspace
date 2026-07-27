# Summary — Issue #49: Clarify `move_file` description (document git-aware behavior)

## Goal

The `move_file` MCP tool **is** git-aware, but the descriptions a client (LLM or human)
actually reads do not say so. They show only *"Move or rename a file or directory"*,
leading readers to wrongly assume a plain filesystem move that loses git rename tracking.

This is a **documentation defect only** — no behavior change.

## Actual behavior (already correct, unchanged)

- `src/mcp_workspace/file_tools/file_operations.py:616` — internal `move_file` decides
  `should_use_git`, calls `_execute_git_move` (which runs `git mv` via
  `git_operations.git_move`) for **git-tracked files**, preserving rename/history.
- For **untracked files or non-git repos** it falls back to a plain filesystem move.
- This module's docstring already documents the behavior correctly → **out of scope**.

Note: the issue cites `file_operations.py:616`; in this tree the file is
`src/mcp_workspace/file_tools/file_operations.py:616` — same code.

## The defect (what we fix)

Three surfaced descriptions omit git-awareness:

1. `src/mcp_workspace/server.py:413` — the `@mcp.tool()` docstring surfaced to MCP clients
   (the actual defect).
2. `README.md:221` — the one-line tool description in the docs table.
3. `README.md:31` — the `move_file` bullet in the Features list.

## Proposed wording

Client-facing docstring summary (`server.py`):

> Move or rename a file or directory within the project. Git-aware: uses `git mv` for
> tracked files (preserving rename/history); falls back to a plain filesystem move for
> untracked files or non-git repos.

README table row (`README.md:221`), kept to a single Markdown table line:

> `| `move_file` | Moves or renames files/directories (git-aware: uses git mv for tracked files, else filesystem move) | "Rename config.js to settings.js" |`

README Features bullet (`README.md:31`), kept to a single line:

> `- `move_file`: Move or rename files and directories (git-aware: uses git mv for tracked files, else filesystem move)`

## Architectural / design changes

**None.** No code paths, signatures, decorators, imports, or data structures change.
This is purely a wording alignment of three human/LLM-facing descriptions so they match
the tool's existing, correct behavior. No new modules, no API surface change.

## TDD applicability

Not applicable. There is no behavior to test-drive — the change is documentation text.
No existing test asserts on the surfaced docstring wording
(`tests/file_tools/test_move_git_integration.py` asserts on the internal result dict's
`method`/`message`, not the docstring), so the wording edit is safe and needs no new test.
Verification is via the mandatory static/quality checks, which must still pass.

## KISS decisions

- Touch the three human-facing descriptions so they all agree (`server.py:413`,
  `README.md:221`, `README.md:31`). Do **not** edit the `README.md:332-336` Move File
  detail section — it already documents git behavior correctly. Avoids doc churn.
- README edit stays a single table line with `| ... |` cell structure intact.

## Files created / modified

| Path | Action | Note |
|------|--------|------|
| `src/mcp_workspace/server.py` | Modify | Expand `move_file` tool docstring summary line (~line 413) |
| `README.md` | Modify | Update `move_file` table row (line 221) and Features bullet (line 31) |
| `pr_info/steps/summary.md` | Create | This document |
| `pr_info/steps/step_1.md` | Create | Single implementation step |

No folders/modules created. `file_operations.py` unchanged (out of scope).

## Steps

- **Step 1** — Update the three surfaced `move_file` descriptions (single commit).
