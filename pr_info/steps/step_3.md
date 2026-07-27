# Step 3 — README documentation

**One commit.** Docs only — no code, no tests. Depends on Steps 1–2 (tool exists).

## WHERE

- `README.md`

## WHAT / HOW

1. **Features list** (~line 28, after the `delete_this_file` bullet): add
   ```
   - `delete_directory`: Delete a directory (empty by default, whole tree with `recursive=True`)
   ```
   Optionally clarify the `delete_this_file` bullet to say "a single file".

2. **Available Tools table** (~line 217, after the `delete_this_file` row): add
   ```
   | `delete_directory` | Deletes a directory (empty, or a whole tree with recursive) | "Delete the pr_info directory and its contents" |
   ```

3. **Tool Details section** (after the delete-file detail block): add a
   `#### Delete Directory` subsection covering:
   - Deletes an **empty** directory by default (`recursive=False`).
   - `recursive=True` deletes the whole tree via `shutil.rmtree`.
   - Handles **directories only** — use `delete_this_file` for files.
   - Idempotent: deleting a missing directory returns a message, not an error.
   - Refuses to delete the project root.
   - Enforces `.gitignore` on the top-level path; a recursive delete still
     removes individually-gitignored **children** (e.g. nested `__pycache__/`).
   - Returns the list of deleted paths (capped at 20 with a summary line).

## DATA

Documentation only. No return values or data structures introduced.

## Checks

No code changed. Optionally run the file-size check; the mandatory pylint/pytest/
mypy trio has nothing to act on but running pytest once to confirm nothing broke
is fine.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Implement Step 3
> only: update `README.md` — add the `delete_directory` features bullet, the
> Available Tools table row, and a `#### Delete Directory` detail subsection, as
> described. Use only MCP workspace tools for the edit. Keep wording consistent
> with the existing entries. Produce exactly one commit's worth of change.
