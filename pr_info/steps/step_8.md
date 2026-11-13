# Step 8 — `.scratch/` migration in this repo

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_8.md`), and issue #83 (`.scratch/` migration, Decisions 8 and 20).
> Implement step 8 only: guard test first, then `.mcp-file-access`, `.gitignore`, and the CLAUDE.md "Scratch probes" section, in the order below.
> Run pylint, pytest (`-n auto`) and mypy; all must pass. Format, then make exactly one commit.
> This step must be last: once `.scratch/` is gitignored, an MCP server that predates this branch refuses `.scratch/` paths, so do no scratch probes after it.

## WHERE

- New: `.mcp-file-access` (repo root)
- `.gitignore`
- `.claude/CLAUDE.md` ("Scratch probes")
- New: `tests/test_repo_access_rules.py`

Not changed: `.github/workflows/ci.yml` — `check-forbidden-folders` keeps blocking a force-added `.scratch/`.

## WHAT

`.mcp-file-access`:

```
# MCP file access rules: <level> <gitignore pattern>; last match wins.
# See README "Access rules (.mcp-file-access)".
read-write  /.scratch/
read-only   /.mcp.json
read-only   /.mcp-file-access
```

`.gitignore` — append:

```
# Agent scratch area (read-write via .mcp-file-access, never committed)
.scratch/
```

`.claude/CLAUDE.md` "Scratch probes" — replace the sentence `` `.scratch/` is not gitignored: the MCP file tools refuse ignored paths.`` with: `` `.scratch/` is gitignored; `.mcp-file-access` makes it read-write for the MCP file tools, and it is never committed. `` Keep the rest (delete when done; CI still blocks a force-added `.scratch/`).

## HOW — order of operations

1. Write the guard test (below); it fails.
2. Create `.mcp-file-access` with `save_file`. If the tool refuses it, write one line to `pr_info/.blocked.txt` ("save_file refused creating .mcp-file-access: <error>") and stop.
3. Create `.scratch/ruff_probe.py` containing `import os` (an unused import ruff must flag) — before `.scratch/` is gitignored.
4. Append `.scratch/` to `.gitignore`.
5. Run `run_ruff_check` on `.scratch/ruff_probe.py` (explicit path). If ruff does not report the unused import, write one line to `pr_info/.blocked.txt` ("run_ruff_check skips explicit .scratch/ path after migration") and stop.
6. `delete_directory(".scratch", recursive=True)`. If the running server refuses it (it predates this branch), leave the folder: it is gitignored and cannot reach the commit.
7. Update `.claude/CLAUDE.md`.

## ALGORITHM

None (configuration).

## DATA

None.

## Tests (`tests/test_repo_access_rules.py`, write first)

Using the repository root (`Path(__file__).resolve().parents[1]`):

- `validate_access_rules(root) == []`.
- `get_file_access(".scratch/probe.py", root) is FileAccess.READ_WRITE`.
- `get_file_access(".mcp.json", root) is FileAccess.READ_ONLY` and `get_file_access(".mcp-file-access", root) is FileAccess.READ_ONLY`.
- `is_path_gitignored(".scratch/probe.py", root) is True` (never committed).

## Follow-up (outside this repo)

MarcusJellinghaus/mcp_coder#1414 switches `verify`'s `.scratch/` smoke test to `get_file_access` and must ship together with this migration. Other repos follow via the Chore Propagation process.
