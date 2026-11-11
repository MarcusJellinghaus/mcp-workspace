# Summary — #251: `github_issue_view(body_file=…)`; file tools keep line endings

## Goal

Make issue-body read-modify-write lossless with mcp-workspace tools, without the body passing
through the model:

```
github_issue_view(N, body_file=".scratch/issue-N.md")   # raw body -> file, byte for byte
  -> edit_file(".scratch/issue-N.md", ...)             # keeps the file's line endings
  -> github_issue_edit(N, body_file=".scratch/issue-N.md")
```

- **Part 1:** `github_issue_view` gains `body_file`. The raw `IssueData["body"]` is written
  verbatim (`newline=""`, UTF-8, no BOM). The reply is the usual view with the body replaced by a
  pointer line, e.g. `(body saved to .scratch/issue-251.md, 488 lines, CRLF)`.
- **Part 2:** `edit_file`, `save_file` and `append_file` stop rewriting files in the platform
  line-ending style:
  - An existing file keeps its ending. A mixed file gets its most common ending; a tie gives the
    platform default.
  - A new file, or one with no line breaks, follows `.gitattributes` `eol=` (`git check-attr`),
    falling back to the platform default.

## Architectural / design changes

| Area | Change |
|---|---|
| New module `file_tools/line_endings.py` | One place for line-ending logic, so `file_operations.py` (730/750 lines) barely grows. Contents: `PLATFORM_NEWLINE` constant (from `os.linesep`, tests monkeypatch it); byte classifier `count_line_endings`; `describe_line_endings` (line count + style for the pointer line); `target_newline` (picks the ending to write). |
| Conversion via `open(newline=…)` | No conversion helper. Content stays LF-normalised as today. Each write site passes the chosen ending as `open(..., newline=nl)`, and Python translates `\n` on write (probed for `"w"`, `"a"` and `mkstemp` fds). `save_body` uses `newline=""`, which writes verbatim. |
| Detection on raw bytes | `count_line_endings(bytes)`: `crlf = count(b"\r\n")`, `lf = count(b"\n") - crlf`, `cr = count(b"\r") - crlf`. No decode, so `save_file` still overwrites non-UTF-8 files. Part 1 runs it on `body.encode("utf-8")`; UTF-8 never uses `\r`/`\n` bytes inside multibyte characters (probed). |
| One read per tool | `target_newline(existing: bytes \| None, rel_path, project_dir)` takes bytes the caller already holds. `edit_file` reads bytes once and decodes them, replacing its text-mode read. |
| `git_operations.get_eol_attribute` | Thin wrapper: `run_git_raw(repo, "check_attr", "-z", "eol", "--", path)` in `safe_repo_context`. No error handling of its own. The only caller (`line_endings._eol_from_gitattributes`) imports it lazily (keeps GitPython off the file-tools import path, like `_determine_move_method`). That caller wraps import and call in one `except Exception` → platform default, which covers git missing (`ImportError`), not a repo, and any git error. |
| `format_issue_view(..., body_note=None)` | Keyword-only. When set, it replaces the body. For an untrusted author only `Title:` stays fenced, and the note follows outside the fence. Without it, output is unchanged. |
| `_github_write_helpers.py` | `check_body_target` (gitignore + containment + not-a-directory, before any GitHub call) and `save_body` (write verbatim, return pointer line), next to `resolve_body`. |
| `github_issue_view` order | path check → fetch issue / comments / linked branches → `save_body` → render. Any error before the write → no file. A write error → `tool_error`, no view. |
| Unchanged | `server.py`; tool registration (`github_issue_view` stays `read_only=True`, documented gap); reading tools (`read_file`, `search_files`, `read_reference_file` still return LF); `edit_file` matching and its LF diff output. |

## Files

### Created
- `src/mcp_workspace/file_tools/line_endings.py`
- `tests/git_operations/test_eol_attribute.py`
- `tests/file_tools/test_line_endings.py`
- `tests/file_tools/test_line_endings_file_tools.py`
- `tests/github_operations/test_formatters_body_note.py`
- `tests/github_operations/test_github_issue_view_body_file.py`

### Modified
- `src/mcp_workspace/git_operations/file_tracking.py` — `get_eol_attribute`
- `src/mcp_workspace/git_operations/__init__.py` — export
- `tests/git_operations/test_init_exports.py` — symbol count 70 → 71
- `src/mcp_workspace/file_tools/edit_file.py` — byte read, `newline=` write
- `src/mcp_workspace/file_tools/file_operations.py` — `save_file`, `_write_file_atomically`, `append_file`
- `src/mcp_workspace/toolset/write.py` — tool docstrings (line-ending behaviour)
- `tests/file_tools/test_edit_file.py` — rewrite `test_crlf_normalization` to assert bytes
- `tests/file_tools/test_file_operations.py` — rewrite the two CRLF tests (`:593`, `:603`) to assert bytes
- `src/mcp_workspace/github_operations/formatters.py` — `body_note`
- `src/mcp_workspace/toolset/_github_write_helpers.py` — `check_body_target`, `save_body`
- `src/mcp_workspace/toolset/github_read.py` — `body_file` parameter and docstring
- `README.md` — edit existing lines only (733/750): tool list `:49`, `:50`, `:53`; table `:374`, `:375`, `:378`, `:384`; untrusted note `:134`
- `docs/LIBRARY_USE.md` — `read_only` note
- `tests/LLM_Test.md` — Test 4.1b round trip

## Steps

1. `get_eol_attribute` in `git_operations`
2. `file_tools/line_endings.py`
3. `edit_file` keeps line endings
4. `save_file` keeps line endings
5. `append_file` becomes a real append in the file's ending
6. `format_issue_view(body_note=…)`
7. `check_body_target` / `save_body` helpers
8. `github_issue_view(body_file=…)` with round-trip tests
9. Docs: README, `LIBRARY_USE.md`, `LLM_Test.md`

## Conventions for every step

- Use the MCP tools (`mcp__mcp-workspace__*`, `mcp__mcp-tools-py__*`), as in `.claude/CLAUDE.md`.
- TDD: write the step's tests first, then the implementation.
- Checks before the commit:
  - `run_pylint_check`
  - `run_pytest_check(extra_args=["-n", "auto"])`
  - `run_mypy_check`
  - `run_lint_imports_check` where imports change
  - then `run_format_code`
- One commit per step.
- Line-ending assertions use `read_bytes()`.
