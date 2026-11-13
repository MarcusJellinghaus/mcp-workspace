# Summary — File access rules via `.mcp-file-access` (#83)

## Goal

Today `.gitignore` is the only access rule: committed paths are read-write, gitignored paths are hidden.
A repo-root rules file `.mcp-file-access` overrides that default per path:

```
# <level> <gitignore pattern>; last match wins
read-write  /.scratch/
read-only   /.mcp.json
```

| Rule | Path would be committed | Path is gitignored |
|---|---|---|
| (no match) | read-write | hidden |
| `read-only` | read-only | readable, listed (walk scope) |
| `read-write` | read-write | read-write, listed, never committed |

Built in, not overridable: `.mcp-file-access` itself is read-only (also when absent); `.git/` is always hidden.
An invalid rules file fails safe: all writes refused, exposures dropped, reads of non-ignored files still work.

The full requirements are issue #83 (Decisions 1–21). This plan does not restate them; each step names the ones it implements.

## Architectural / design changes

### New layer: access = gitignore default + rules override

```
toolset/*  ──► toolset/_context.py  check_readable / check_writable   (enforcement, MCP-free)
                    │
                    ▼
file_tools/directory_utils.py
    FileAccess (IntEnum: HIDDEN < READ_ONLY < READ_WRITE)
    _access(path, project_dir, rules) -> (FileAccess, reason)     # one spelling-aware core
    get_file_access / require_access / check_tree_access          # public helpers
    list_accessible_files (walk with exposure, Decision 15)
                    │
                    ▼
file_tools/access_rules.py   (new, pure parsing + matching)
    AccessRules, load_access_rules, validate_access_rules, access_rules_warning
```

- **One core function** `_access` decides everything: `.git` → hidden; invalid rules file → committed read-only / ignored hidden; else last matching rule overrides the gitignore default; the rules file is capped at read-only. It returns the most restrictive result across the spellings `is_path_gitignored` already checks (as given, canonical, resolved through links).
- **Matching engine:** `PathSpec.from_lines("gitignore", …)` with `check_file().index` (last match wins in both directions). Patterns and paths lower-cased on win32; directories passed with a trailing `/`.
- **No cache:** the rules file is read once per tool call (passed down to walks and tree checks), never across calls.
- **Gitignore-only API unchanged:** `is_path_gitignored`, `check_path_not_gitignored`, `list_files` keep their meaning, so `check_file_size` and mcp_coder's `list_files` uses are unaffected.

### Simplifications chosen (KISS)

1. **One check function** `require_access(path, project_dir, needed)` raises every refusal message; `toolset/_context.py` wraps it as `check_readable` / `check_writable`. `check_not_gitignored` is removed. `read_reference_file` calls `require_access` directly.
2. **Tree checks use the rules file for "read-only by rule"** — no per-file gitignore lookup for `delete_directory`. Only `move_file`'s Decision 21 check needs gitignore, and only for files the cheap per-directory predicate (`_gitignore_skip`) reports as ignored. One function `check_tree_access(src, dest | None)` serves both tools; a single file is a tree of one.
3. **Listing reuses `_discover_files`** with a skip predicate wrapping `_gitignore_skip`: an entry is skipped when gitignore skips it and no rule exposes it. igittigitt already reports every entry below an ignored directory as ignored, so inside such a directory only rule-matched paths survive — no separate walk.
4. **`tree_listing.py` is unchanged.** Suffixes are appended to file paths before `list_directory_tree` (`"uv.lock (read-only)"` is just a file name to the tree builder), so collapsed `dir/ (N files)` lines and `dirs_only` output stay unmarked automatically. The warning line is prepended after rendering, so it does not count towards the 250-line cap.
5. **Move method:** `_determine_move_method` gets a `dest_ignored` flag; a gitignored destination always uses a plain filesystem move.

### Decisions this plan makes (open points of the discussion, resolved with the recommended default)

| Topic | Decision |
|---|---|
| `github_issue_view(body_file=…)` | It writes a file, so its target gets the **write** check (`check_body_target`): refused on read-only paths, allowed into `.scratch/`. |
| Exception type for a refused write | `ValueError`, like the gitignore refusal. |
| Refused write, invalid rules file | `No write access to '<path>' (.mcp-file-access is invalid: line 3: unknown level 'readonly')` |
| Move that would expose a hidden file | `Move refused: '<src>' contains files hidden by .gitignore rules that would become accessible at '<dest>'` (names no file). |
| Refused read of a hidden path | Unchanged gitignore message (`Path '<p>' is excluded by .gitignore rules …`). |
| Listing warning line | `WARNING: .mcp-file-access is invalid (<problems joined by '; '>) - writes are refused and no gitignored path is exposed.` |
| Built-in rules file in listings | `.mcp-file-access` at the root gets `(read-only)` like a rule match (it differs from the default). |
| Listing below an ignored ancestor | A directory is listable when every ignored directory on its path is enterable (rule matches it, or an anchored rule's literal prefix leads into it) — the same set the root walk reaches. |

## Files created or modified

### Created
- `src/mcp_workspace/file_tools/access_rules.py` — rules parsing, matching, validation, warning line.
- `tests/file_tools/test_access_rules.py` — parser tests (step 1).
- `tests/file_tools/test_file_access.py` — effective access tests (step 2).
- `tests/test_file_access_tools.py` — single-path tool enforcement (step 3).
- `tests/test_file_access_trees.py` — `move_file` / `delete_directory` tree checks (step 4).
- `tests/file_tools/test_accessible_listing.py` — walk, search, reference listing (step 5).
- `tests/test_file_access_listing.py` — `list_directory` suffixes / warning / hidden dir (step 6).
- `.mcp-file-access` — this repo's rules (step 8).

### Modified
- `src/mcp_workspace/file_tools/directory_utils.py` — `FileAccess`, `_access`, `get_file_access`, `require_access`, `check_tree_access`, `list_accessible_files`, re-export of `validate_access_rules`.
- `src/mcp_workspace/file_tools/__init__.py` — exports.
- `src/mcp_workspace/file_tools/file_operations.py` — `_determine_move_method(…, dest_ignored)`, `move_file` docstring.
- `src/mcp_workspace/file_tools/search.py` — uses `list_accessible_files`.
- `src/mcp_workspace/toolset/_context.py` — `check_readable` / `check_writable` replace `check_not_gitignored`.
- `src/mcp_workspace/toolset/read.py`, `write.py`, `delete.py`, `move.py`, `reference.py`, `github_write.py`, `_github_write_helpers.py` — switch to the new checks / listing; docstrings.
- Existing tests: `tests/test_server.py` (imports `check_not_gitignored`), `tests/test_server_list_directory.py` and `tests/test_reference_projects_mcp_tools.py` (patch `list_files_util`).
- Docs: `README.md`, `SECURITY.md`, `docs/ARCHITECTURE.md`, `docs/release-notes.md`, `.claude/CLAUDE.md`.
- `.gitignore` — adds `.scratch/` (step 8).

### Not modified (on purpose)
- `file_tools/tree_listing.py`, `checks/file_sizes.py`, `toolset/checks.py`, `.github/workflows/ci.yml` (the `check-forbidden-folders` job keeps working).

## Steps

1. Rules file parser (`access_rules.py`).
2. Effective access and public API.
3. Single-path enforcement in the tools.
4. Tree checks for `move_file` / `delete_directory`; filesystem move into a gitignored destination.
5. Exposure-aware listing walk for `search_files` and the reference listing / search.
6. `list_directory`: exposed paths, suffixes, warning line, listing a hidden directory.
7. Docs.
8. `.scratch/` migration (ships together with MarcusJellinghaus/mcp_coder#1414).
