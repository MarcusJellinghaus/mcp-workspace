# Step 2 — Effective access and public API

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_2.md`), and issue #83 (Rules file table, Built in, Constraints: Spellings, Public API).
> Implement step 2 only: tests first, then the access core in `src/mcp_workspace/file_tools/directory_utils.py` and the exports.
> No tool changes yet. Run pylint, pytest (`-n auto`) and mypy; all must pass. Format, then make exactly one commit.

## WHERE

- `src/mcp_workspace/file_tools/directory_utils.py` (module path must stay — mcp_coder imports from it)
- `src/mcp_workspace/file_tools/__init__.py`
- New: `tests/file_tools/test_file_access.py`

## WHAT

```python
class FileAccess(IntEnum):
    HIDDEN = 0
    READ_ONLY = 1
    READ_WRITE = 2

def _spellings(path: str, project_dir: Path) -> set[str]: ...           # extracted from is_path_gitignored
def _access(path: str, project_dir: Path, rules: AccessRules) -> tuple[FileAccess, str]: ...
def get_file_access(path: str, project_dir: Path) -> FileAccess: ...
def require_access(file_path: str, project_dir: Path, needed: FileAccess) -> None: ...
```

Re-export: `from mcp_workspace.file_tools.access_rules import validate_access_rules as validate_access_rules` (explicit re-export form, so ruff/mypy accept it). Export `FileAccess`, `get_file_access`, `validate_access_rules` from `file_tools/__init__.py` (`__all__`).

## HOW

- `_spellings` returns `{path, canonical_spelling(path), _resolved_relative(...)}` minus `None`; `is_path_gitignored` uses it (behaviour unchanged).
- Move the gitignore refusal text into a private helper `_excluded_error(file_path) -> ValueError`, used by both `check_path_not_gitignored` and `require_access` (same wording).
- `is_path_gitignored`, `check_path_not_gitignored`, `list_files` keep their gitignore-only meaning.

## ALGORITHM

```
_access(path, project_dir, rules):
    if is_path_in_git_dir(path) or resolves_into_git_dir(project_dir / path, project_dir): return (HIDDEN, "")
    return min((_one(s) for s in _spellings(path, project_dir)), key=lambda r: r[0])   # most restrictive
_one(rel):
    ignored = _matches_rules(rel, project_dir); rule = rules.match(rel, is_dir=(project_dir / rel).is_dir())
    base = level of rule if rule else (HIDDEN if ignored else READ_WRITE)
    if rel is the rules file (casefold on win32): return (min(base, READ_ONLY), "built-in")
    if rules.problems: return (HIDDEN if ignored else READ_ONLY, ".mcp-file-access is invalid: " + "; ".join(problems))
    return (base, f"rule '{rule.pattern}' in .mcp-file-access" if rule else "")
```

```
require_access(file_path, project_dir, needed):
    absolute path -> relative to project_dir (outside -> return; normalize_path refuses later)
    access, reason = _access(rel, project_dir, load_access_rules(project_dir))
    HIDDEN -> raise _excluded_error(file_path)
    needed is READ_WRITE and access is READ_ONLY -> raise ValueError(f"No write access to '{rel}' ({reason})")
```

## DATA

- `get_file_access` → `FileAccess` member.
- Reasons: `""` (default), `"rule '<pattern>' in .mcp-file-access"`, `"built-in"`, `".mcp-file-access is invalid: <problems>"`.
- Refusal: `No write access to '<path>' (<reason>)`, `ValueError`.

## Tests (`tests/file_tools/test_file_access.py`, write first)

Build projects in `tmp_path` with a `.gitignore` and a `.mcp-file-access`.

- Default: committed → `READ_WRITE`, ignored → `HIDDEN`; no rules file → identical to `is_path_gitignored`.
- `read-only` on committed and on ignored → `READ_ONLY`; `read-write` on ignored → `READ_WRITE`.
- Last match wins both ways (`read-only config/` then `read-write config/local.json`).
- Directory path `.scratch` (exists) under `read-write /.scratch/` → `READ_WRITE`.
- Directory rule exposes an ignored `.env` below it (`read-only /config/`, `.gitignore` `.env`) → `config/.env` is `READ_ONLY`.
- Unanchored rule deep inside an ignored directory (`read-only *.log`, `logs/` ignored) → `logs/a.log` is `READ_ONLY` (access honours any depth).
- Rules file: `READ_ONLY` with reason `built-in`, also when absent and even with `read-write /.mcp-file-access`; `.mcp-file-access.` and `.mcp-file-access::$DATA` → `READ_ONLY`.
- Protected spellings: `.mcp.json.` and `.mcp.json::$DATA` under `read-only /.mcp.json` → `READ_ONLY`; `.MCP.json` → `READ_ONLY` (win32 only, `skipif`).
- Symlink to a read-only file → `READ_ONLY` (skip when symlinks are unavailable, as `tests/test_file_tool_path_rules.py` does).
- `read-write /.git/` rule → `.git/config` still `HIDDEN`.
- Invalid file: committed path → `READ_ONLY` with the invalid reason; ignored path with a `read-only` rule → `HIDDEN`.
- `require_access`: hidden → gitignore message; read-only + `READ_WRITE` needed → exact `No write access to '<path>' (rule '/.mcp.json' in .mcp-file-access)`; read-only + `READ_ONLY` needed → no error; absolute path inside the project is checked.
- `validate_access_rules` importable from `mcp_workspace.file_tools.directory_utils` and `mcp_workspace.file_tools`.
