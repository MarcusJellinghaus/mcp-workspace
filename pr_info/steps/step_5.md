# Step 5 — Exposure-aware listing walk for `search_files` and the reference listing / search

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_5.md`), and issue #83 (Tool behaviour rows `search_files` / reference tools, Public API, Decisions 13, 15, 19, Constraints: Directory walk vs #392).
> Implement step 5 only: tests first, then `list_accessible_files` and its use in `search_files`, `list_reference_directory` and `search_reference_files`.
> `list_directory` switches in step 6. Run pylint, pytest (`-n auto`) and mypy; all must pass. Also run the performance tests serially (`markers=["performance"]`, `-n 0`). Format, then make exactly one commit.

## WHERE

- `src/mcp_workspace/file_tools/directory_utils.py`
- `src/mcp_workspace/file_tools/search.py`
- `src/mcp_workspace/toolset/reference.py`
- `tests/test_reference_projects_mcp_tools.py` (patches `list_files_util` in `toolset.reference`)
- New: `tests/file_tools/test_accessible_listing.py`

## WHAT

```python
@dataclass(frozen=True)
class AccessListing:
    files: list[str]            # project-relative, forward slashes, sorted as _discover_files returns them
    notes: dict[str, str]       # path -> "(read-only)" | "(read-write, not committed)"; empty when rules are invalid
    problems: list[str]         # rules-file problems; [] when valid

def _enterable(rel_dir: str, project_dir: Path, rules: AccessRules) -> bool: ...
def list_accessible_files(directory: str | Path, project_dir: Path) -> AccessListing: ...
```

## HOW

- Reuse `_discover_files(abs_path, project_dir, skip)`; the new `skip` wraps `_gitignore_skip(abs_path, project_dir)`. No second walker.
- Load the rules once per call (`load_access_rules`) and pass them down.
- `list_files` is unchanged (gitignore-only; `check_file_size` and mcp_coder keep using it).
- `search.search_files`: `all_files = list_accessible_files(".", project_dir).files` (paths unmarked).
- `reference.list_reference_directory`: `listing = list_accessible_files(".", ref_path)`; return `[warning] + listing.files` when `access_rules_warning(listing.problems)` is not `None`, else `listing.files`. No suffixes. Update its docstring (first line may be a warning).
- `search_reference_files` needs no change (shares `search_files`).

## ALGORITHM

```
skip(path):                                   # path absolute; rel = project-relative posix
    if not gitignored(path): (if path is a file: note_for(rel, ignored=False)); return False
    if path.is_dir(): return not _enterable_here(rel)       # rules.match(rel, is_dir=True) or rules.leads_into(rel)
    if rules.match(rel) is None and not rules-file: return True       # cheap rejection first
    if _access(rel, project_dir, rules)[0] is HIDDEN: return True     # spellings / link to hidden target
    note_for(rel, ignored=True); return False
note_for(rel, ignored): rule level read-only (or the root rules file) -> "(read-only)"; read-write and ignored -> "(read-write, not committed)"
```

```
list_accessible_files(directory, project_dir):
    abs_path, rel_path = normalize_path(...); missing -> FileNotFoundError; file -> NotADirectoryError
    if rel_path is not "." and not _enterable(rel_path): raise _excluded_error(directory)
    files = _discover_files(abs_path, project_dir, skip); return AccessListing(files, notes, list(rules.problems))
_enterable(rel_dir): every ancestor-or-self A of rel_dir that is gitignored must satisfy rules.match(A, is_dir=True) or rules.leads_into(A)
```

With invalid rules `rules.rules == ()`, so nothing is exposed and no notes are produced — exactly the gitignore listing.

## DATA

`AccessListing` as above. Refusal for a hidden, non-enterable directory: the gitignore message (`ValueError`).

## Tests (`tests/file_tools/test_accessible_listing.py`, write first)

- No rules file → `files == list_files(".", project_dir)`.
- Logs: `.gitignore` `*.log` and `logs/`, rule `read-only /logs/` → `logs/a.log` and `logs/sub/b.log` listed with note `(read-only)`; `search_files(pattern=...)` finds text inside them.
- Walk scope: `read-only *.log` with `logs/` ignored → `logs/a.log` **not** listed / not searched (but `get_file_access` is `READ_ONLY`); a root-level ignored `x.log` is listed.
- Anchored prefix: `read-only /logs/sub/*.log` → `logs/sub/b.log` listed, `logs/a.log` not.
- Directory rule exposes ignored files below (`read-write /.scratch/`, `.scratch/__pycache__/m.pyc` and `.scratch/.env`) → both listed with `(read-write, not committed)`.
- `read-only /plain.txt` on a committed file → listed with `(read-only)`; `read-write` on a committed file → no note.
- Root `.mcp-file-access` → note `(read-only)`.
- Invalid rules file → exposed paths gone, `notes == {}`, `problems` non-empty.
- `list_accessible_files("logs")` works under `read-only /logs/`; `list_accessible_files("secret")` (ignored, no rule) raises the gitignore message.
- `check_file_size` (`checks/file_sizes.py`) still excludes exposed files.
- Reference project with its own rules file: `list_reference_directory` and `search_reference_files` include exposed paths without suffixes; invalid rules file → first line of `list_reference_directory` is the warning.
- Update `tests/test_reference_projects_mcp_tools.py` mocks to patch the new call (`list_accessible_files`).
