# Summary — #405: win32 pattern lower-casing breaks matching; `re.error` escapes

## Problem

1. A reversed character range (`[b-a]x`, or `[Z-a]x` once lower-cased on win32)
   makes pathspec raise `re.error`. That is not a `ValueError`, so it escapes:
   - `.mcp-file-access`: `load_access_rules` crashes, and so does every caller
     (`get_file_access`, `require_access`, `check_tree_access`,
     `list_accessible_files`, `validate_access_rules`, `search_files`, the
     reference tools), instead of the file being flagged invalid.
   - `search_files` / `search_reference_files`: `_match_glob` raises `re.error`,
     although its docstring promises a `ValueError`.
2. On win32 both modules lower-case the pattern text to get case-insensitive
   matching. That changes what a pattern means: `[A-z]x` matches `_x`, but
   the folded `[a-z]x` does not. Paths are matched wrongly with no error.

## Architectural / design changes

- **Case-insensitivity moves from text folding into the regex.** A new mixin
  `_CaseInsensitiveOnWin32(RegexPattern)` overrides the classmethod
  `pattern_to_regex` and puts `(?i)` (`b"(?i)"` for bytes) in front of the
  generated regex when `sys.platform == "win32"`; a `None` regex (comments)
  is left alone. `sys.platform` is read each time a spec is built, so tests
  can monkeypatch it.
- **Two thin pattern classes, one per existing semantics** (both in
  `access_rules.py`):
  - `AccessRulePattern(_CaseInsensitiveOnWin32, GitIgnoreBasicPattern)`,
    used by `PathSpec.from_lines(AccessRulePattern, …)`. Same semantics as
    the current `"gitignore"` factory.
  - `GlobPattern(_CaseInsensitiveOnWin32, GitIgnoreSpecPattern)`, used by
    `GitIgnoreSpec.from_lines(…, GlobPattern)` in `search.py`. Same
    semantics as the current `GitIgnoreSpec` default.

  Two classes because `GitIgnoreSpec.from_lines` rejects any
  `GitIgnoreBasicPattern` subclass (`TypeError`), and switching access rules
  to the Spec class would change what rules mean.
- **No lower-casing for matching.** Patterns and paths are matched as given.
  `_fold` stays only for the literal-prefix string comparison in
  `AccessRules.leads_into`.
- **`re.error` is caught next to `ValueError`:**
  - `_compiles` returns False, so the line is reported as
    `line N: invalid pattern '<p>'` and the file is invalid;
  - `_match_glob` maps it to the documented "matches nothing by construction"
    `ValueError`.
  - `_compiles` validates with the same class that builds the final spec, so
    `load_access_rules` needs no try/except.
- **New dependency edge:** `file_tools/search.py` → `file_tools/access_rules.py`.
  No import cycle, because `access_rules.py` imports nothing from `file_tools`.
- **Unchanged:**
  - the gitignore pattern semantics of access rules and globs;
  - case-insensitivity is still win32 only;
  - error messages;
  - public API.

## Files modified

| File | Change |
|---|---|
| `src/mcp_workspace/file_tools/access_rules.py` | mixin + `AccessRulePattern` + `GlobPattern`; `_compiles` catches `re.error`; no `_fold` in `load_access_rules` / `match`; `_fold` docstring |
| `src/mcp_workspace/file_tools/search.py` | `_match_glob` uses `GlobPattern`, maps `re.error` → `ValueError`, no `.lower()`; `import sys` removed |
| `tests/file_tools/test_access_rules.py` | `[b-a]x` invalid case; win32 fixture + parametrized match test (replaces skip-gated test); bytes test; semantics regression test |
| `tests/file_tools/test_search.py` | `[b-a]x` in `TestSearchFilesGlobValidation`; win32 fixture + parametrized `_match_glob` test |
| `docs/ARCHITECTURE.md` | access-rules matching line; `access_rules.py` description |
| `docs/release-notes.md` | new top section for #405 (search part only) |

No new files, folders or modules (apart from these plan files).

## Steps

1. [step_1.md](step_1.md): pattern classes and the access-rules fix (`access_rules.py`, its tests, `ARCHITECTURE.md` matching line).
2. [step_2.md](step_2.md): `search_files` fix (`search.py`, its tests, `ARCHITECTURE.md` module line, release note).

## After implementation (not a commit)

The Obsidian note `Repos/mcp-workspace.md` ("Windows matching is
case-insensitive by design") says the tool lower-cases both pattern and paths.
After this change that is wrong. Write a `Field Notes/` entry,
`Promote into [[mcp-workspace]]`, following `Conventions.md`.
