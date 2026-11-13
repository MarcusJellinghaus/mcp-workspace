# Step 6 — `list_directory`: exposed paths, suffixes, warning line, listing a hidden directory

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_6.md`), and issue #83 (Tool behaviour row `list_directory`, Invalid rules file, Decisions 6, 15, 17).
> Implement step 6 only: tests first, then switch `list_directory` in `toolset/read.py` to `list_accessible_files`.
> `file_tools/tree_listing.py` stays unchanged. Run pylint, pytest (`-n auto`) and mypy; all must pass. Format, then make exactly one commit.

## WHERE

- `src/mcp_workspace/toolset/read.py`
- `tests/test_server_list_directory.py` (patches `list_files_util`)
- New: `tests/test_file_access_listing.py`

## WHAT

`list_directory(path=".", dirs_only=False) -> list[str]` — signature unchanged; body switches to `list_accessible_files`.

## HOW

- Imports: `list_accessible_files` from `mcp_workspace.file_tools.directory_utils`, `access_rules_warning` from `mcp_workspace.file_tools.access_rules`. Drop the `list_files_util` import from `read.py` if nothing else uses it.
- Keep the "is a file" refusal: if the path is a file, run `check_readable(ctx, path)` first (a hidden file keeps the gitignore message), then raise the existing `is a file` error.
- A hidden directory is refused by `list_accessible_files` unless the walk enters it (step 5).
- Suffix = `" " + note` appended to the file path before `list_directory_tree`; the tree builder treats it as part of the file name, so collapsed and `dirs_only` lines stay unmarked.
- Warning line prepended after rendering → not counted in the 250-line cap.
- Docstring Returns: file lines may end in ` (read-only)` or ` (read-write, not committed)` — strip the suffix before passing the path to `read_file`; the first line may be a `WARNING:` about an invalid `.mcp-file-access`. Raises: "excluded by .gitignore rules and not exposed by .mcp-file-access".

## ALGORITHM

```
abs_path, rel_path = normalize_path(path, ctx.project_dir)
if abs_path.is_file(): check_readable(ctx, path); raise ValueError(f"'{path}' is a file, not a directory. Use read_file() instead.")
listing = list_accessible_files(path, ctx.project_dir)
entries = [f"{p} {listing.notes[p]}" if p in listing.notes else p for p in listing.files]
lines = list_directory_tree(entries, base_path=rel_path, dirs_only=dirs_only)
warning = access_rules_warning(listing.problems); return [warning, *lines] if warning else lines
```

## DATA

`list[str]`: optional warning line, then the rendered tree lines (unchanged format apart from file-line suffixes).

## Tests (`tests/test_file_access_listing.py`, write first)

- Suffixes: ignored `uv.lock` under `read-only /uv.lock` → `"uv.lock (read-only)"`; `.scratch/p.py` under `read-write /.scratch/` → `".scratch/p.py (read-write, not committed)"`; committed `.mcp.json` under `read-only /.mcp.json` → `".mcp.json (read-only)"`; unmatched files unmarked.
- `dirs_only=True` → no suffix anywhere.
- Collapsed directory holding exposed files (>250 entries) → its `dir/ (N files)` line is unmarked and `N` counts the exposed files.
- Hidden directory with exposed files: `list_directory("logs")` under `read-only /logs/` (`logs/` ignored) → only the exposed paths.
- Hidden directory without a rule → refused with the gitignore message.
- Nonexistent ignored directory (`.gitignore` `secret/`, `list_directory("secret")` with no `secret/` on disk) → refused with the gitignore message, not "does not exist".
- `.git/` always refused: with a `read-write /.git/` rule, `list_directory(".git")` → refused (`normalize_path`'s "inside a git directory" error, which fires first; `_enterable`'s `.git` short-circuit is defense in depth for direct `list_accessible_files` callers).
- Invalid rules file → first line starts with `WARNING: .mcp-file-access is invalid`, no suffixes; with more than 250 entries the output is warning + 250 lines + the truncation summary.
- A file path → `is a file` error; a hidden file path → gitignore message.
- Update `tests/test_server_list_directory.py`: patch `mcp_workspace.toolset.read.list_accessible_files` (return an `AccessListing`) instead of `list_files_util`.
