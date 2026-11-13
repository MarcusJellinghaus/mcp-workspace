# Step 7 — Docs

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_7.md`), and issue #83 (Docs, Constraints: Threat model, Not a sandbox).
> Implement step 7 only: documentation. No code changes. Run pylint, pytest (`-n auto`) and mypy (they must still pass). Make exactly one commit.

## WHERE

- `README.md`
- `SECURITY.md`
- `docs/ARCHITECTURE.md`
- `docs/release-notes.md`

## WHAT

### `README.md`
- **Path Confinement** — after the gitignore bullets, add an "Access rules (`.mcp-file-access`)" subsection:
  - format `<level> <gitignore pattern>`, levels `read-only` / `read-write`, last match wins, `#` comments, no `!`;
  - the effective-access table (committed / gitignored × no match / read-only / read-write);
  - built in: `.mcp-file-access` is read-only (also when absent), `.git/` always refused;
  - directory rules expose everything below, including other ignored files — prefer narrow anchored patterns;
  - walk scope: an ignored directory is listed and searched only when a rule matches it or an anchored rule's literal prefix leads into it;
  - logs example: `read-only /logs/` (listed and searchable) versus `read-only *.log` (readable by exact path, but not listed or searched inside an ignored `logs/`);
  - refusal message format; invalid file fails safe (writes refused, exposures dropped) and is reported in write errors, as the first `list_directory` line, and in the log;
  - "Not a sandbox": rules cover the MCP file tools only; native client tools and the `git` tool bypass them.
- **Tool Details** — `List Directory` (suffixes, warning line), `Move File` (refusals; a move into a gitignored destination is a plain filesystem move, so the file ends up untracked), `Delete Directory` (refused when any file in the tree is read-only), `Check File Size` (still excludes every gitignored file).
- Replace the sentence "Gitignored paths … are rejected for reading and writing" with wording that points to the rules subsection.

### `SECURITY.md`
- **Threat Model**: the rules defend against the agent widening its own access through the MCP file tools; not a sandbox.
- **Intended Restrictions** (File tools): paths read-only by `.mcp-file-access` refuse every write tool (incl. `move_file` / `delete_directory` trees and `github_issue_view` `body_file`); `.mcp-file-access` itself is never writable through the file tools; a move never makes a hidden file accessible.
- **Scope**: writing a read-only path or editing `.mcp-file-access` through MCP tools is an in-scope vulnerability; adjust "file tools reaching … the content of gitignored paths" to "… not exposed by `.mcp-file-access`".

### `docs/ARCHITECTURE.md`
- Section 6: `_discover_files` also feeds `list_accessible_files` (exposure-aware skip predicate).
- New short section "Access layer": `access_rules.py` (parse / match) → `directory_utils._access` (gitignore default + rules override, spelling-aware) → `toolset/_context.check_readable` / `check_writable`; `list_files` stays gitignore-only for `check_file_size` and library callers.

### `docs/release-notes.md`
New top entry `## Next minor release — file access rules via .mcp-file-access (#83)`:
- the rules file and levels; listing suffixes and warning line; `search_files` includes exposed files; `check_file_size` unchanged;
- new refusals (`No write access …`), tree checks, move into a gitignored destination is untracked;
- new public API: `FileAccess`, `get_file_access`, `validate_access_rules` (in `file_tools` and `file_tools.directory_utils`); `is_path_gitignored`, `check_path_not_gitignored`, `list_files` unchanged;
- `toolset._context.check_not_gitignored` removed (internal).

## HOW / ALGORITHM / DATA

Not applicable (docs only). Keep each doc's existing style and heading levels; no restating of the issue's rationale beyond what a user needs.
