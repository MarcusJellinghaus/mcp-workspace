# Step 3 — LF default via `fs.dominant_newline`; remove `PLATFORM_NEWLINE`

The one intended behaviour change: tie, no line breaks, or new file →
`.gitattributes` `eol=`, else **LF** (was the platform default).

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md` exactly.
> TDD: rework the tests first (they fail until `PLATFORM_NEWLINE` is gone and the
> fallback is LF), then change the code and wording. Use the MCP tools only. Run
> the checks below; all must pass. Then run `run_format_code` and make exactly one commit.

## Tests first

Rules for every `monkeypatch.setattr(line_endings, "PLATFORM_NEWLINE", …)` (20 calls):
- Patch is only a dummy, or the test neither proves `eol=` wins nor asserts the
  fallback → **delete the patch line**, keep the assertions.
- Test asserts the platform fallback → rename `…_uses_platform` / `…_use_platform`
  to `…_uses_lf` / `…_use_lf`, drop the `platform` parametrization, assert `"\n"` /
  `b"\n"` unconditionally, docstring says LF.
- Drop `from mcp_workspace.file_tools import line_endings` where it becomes unused.

### `tests/file_tools/test_line_endings.py`
- `_record_lookups(monkeypatch, value: str | None = "lf") -> list[str]` — the stub returns `value`.
- `test_target_newline_tie_uses_platform` → `test_target_newline_tie_uses_lf`:
  `calls = _record_lookups(monkeypatch, None)`; both tie inputs → `"\n"`;
  `assert calls == ["x.txt", "x.txt"]` (lookup now runs on a tie).
- `test_target_newline_follows_eol_attribute`: delete patch.
- `test_target_newline_other_eol_values_use_platform` → `…_use_lf`.
- `test_target_newline_lookup_error_uses_platform` → `…_uses_lf`.
- `test_target_newline_without_project_dir_uses_platform` → `…_uses_lf` (still `assert not calls`).
- `test_target_newline_reads_gitattributes`: delete patch; `.gitattributes`
  `*.bat eol=crlf`, `target_newline(None, "x.bat", tmp_path) == "\r\n"`; docstring
  "A real repository's eol=crlf rule is read."
- `test_target_newline_outside_repository_uses_platform` → `…_uses_lf`.

### `tests/file_tools/test_line_endings_file_tools.py`
- Ties → `_patch_lookup(monkeypatch, None)` (records calls), expect LF and
  `calls == ["f.txt"]`:
  `test_edit_file_tie_uses_platform` → `…_uses_lf` (bytes `b"a\nb\nx"`),
  `test_save_file_tie_uses_platform` → `…_uses_lf` (bytes `b"x\ny\n"`).
- `test_save_file_new_file_follows_gitattributes`: parametrize `(name, nl)` —
  `[("run.sh", b"\n"), ("run.bat", b"\r\n")]`; delete patch; docstring drops
  "over the platform".
- `test_save_file_new_file_without_repo_uses_platform` → `…_uses_lf`.
- `test_append_file_no_breaks_without_eol_uses_platform` → `…_uses_lf`.
- Delete patch only: `test_edit_file_no_breaks_follows_eol_attribute`,
  `test_edit_file_empty_file_prepend_follows_eol_attribute`,
  `test_save_file_crlf_content_onto_lf_file`, `test_save_file_mixed_gets_majority`,
  `test_save_file_no_breaks_follows_eol_attribute`,
  `test_append_file_mixed_keeps_bytes_appends_majority`,
  `test_append_file_no_breaks_follows_eol_attribute`.

### `tests/file_tools/test_file_operations.py`
- `test_save_file_normalizes_crlf`: delete the patch (and the `monkeypatch`
  parameter if unused), keep the LF assertion, docstring "… to a new file as LF.";
  drop the `line_endings` import.

## WHERE / WHAT / HOW — `src/mcp_workspace/file_tools/line_endings.py`

- Remove `import os` and `PLATFORM_NEWLINE` (with its comment).
- Import `dominant_newline` from `mcp_coder_utils.fs` (with `count_line_endings`).

## ALGORITHM

```python
def target_newline(existing: bytes | None, rel_path: str, project_dir: Path | None) -> str:
    return dominant_newline(existing or b"") or _eol_from_gitattributes(rel_path, project_dir)

def _eol_from_gitattributes(rel_path, project_dir) -> str:
    if project_dir is None: return "\n"
    try: value = get_eol_attribute(rel_path, project_dir)   # lazy import kept
    except Exception: log debug; return "\n"
    return {"lf": "\n", "crlf": "\r\n"}.get(value or "", "\n")
```

## DATA

`target_newline -> "\n" | "\r\n" | "\r"`; `_eol_from_gitattributes -> "\n" | "\r\n"`.

## Wording — one merged rule, not a literal "platform default" → "LF" replace

Rule: existing file with line breaks → its dominant ending; tie, no line breaks or
new file → `.gitattributes` `eol=`, else LF.

- `line_endings.py`: `target_newline` and `_eol_from_gitattributes` docstrings;
  pylint comment → `# git missing / not a repo / any git error -> LF`.
- `edit_file.py` `edit_file` docstring: "Line endings: an existing file with line
  breaks keeps its dominant ending; a tie or no line breaks follows .gitattributes
  eol=, else LF. Matching and the returned diff use LF."
- `file_operations.py` `append_file` docstring: "… the appended text uses the
  file's dominant ending (tie or no line breaks → .gitattributes eol=, else LF). …"
- `toolset/write.py`:
  - save_file: "Line endings: overwriting a file with line breaks keeps its dominant
    ending; a new file, a tie, or no line breaks follows .gitattributes eol=, else LF."
  - append_file: as the `append_file` docstring above.
  - edit_file: as the `edit_file` docstring above.

## `docs/release-notes.md`

New top section:

```markdown
## Next minor release — file tools use mcp-coder-utils fs; LF default (#400)

- New files, files without line breaks, and ties in mixed files get `.gitattributes` `eol=`, else LF (was the platform default, CRLF on Windows); existing files with a dominant ending keep it.
```

## Checks

`run_pylint_check`, `run_pytest_check(extra_args=["-n", "auto"])`, `run_mypy_check`,
`run_ruff_check`, `run_tach_check`, `run_lint_imports_check`, `run_vulture_check`.
Also `search_files` for `PLATFORM_NEWLINE` and `platform default` under `src/` and
`tests/` → no matches.

## Commit

`feat(file_tools): default to LF when no dominant ending and no eol= attribute`
