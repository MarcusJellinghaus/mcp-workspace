# Step 4 — `save_file` keeps line endings

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md`: make `save_file`
> write in the target's existing line-ending style, or the `eol=` / platform default for new
> files. Write and rewrite the tests first. Run pylint, pytest (`-n auto`) and mypy, all green.
> Run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/file_tools/file_operations.py` — `save_file`, `_write_file_atomically`
  (the file is at 730/750 lines: keep the change to a few lines)
- `src/mcp_workspace/toolset/write.py` — `save_file` tool docstring
- `tests/file_tools/test_file_operations.py` — rewrite `test_save_file_normalizes_crlf` (`:593`)
- `tests/file_tools/test_line_endings_file_tools.py` — add tests

## WHAT

```python
def _write_file_atomically(abs_path: Path, rel_path: str, content: str, newline: str) -> bool:
```

`save_file` keeps its signature.

## HOW

- Leave `_validate_save_parameters` unchanged. It still LF-normalises, and `append_file` shares it.
- Work out the ending **before** `_write_file_atomically`: that function unlinks the target first
  on Windows (`:273-274`).
- The temp file uses `open(temp_fd, "w", encoding="utf-8", newline=newline)`.
- Import `target_newline` from `mcp_workspace.file_tools.line_endings`.

## ALGORITHM

```
abs_path, rel_path, content = _validate_save_parameters(...)
existing = abs_path.read_bytes() if abs_path.is_file() else None
newline = target_newline(existing, rel_path, project_dir)
_create_parent_directories(abs_path)
return _write_file_atomically(abs_path, rel_path, content, newline)
```

## Tests

- **Rewrite `test_save_file_normalizes_crlf`:** on a new file with `PLATFORM_NEWLINE`
  monkeypatched to `"\n"` and no git repo, CRLF content → `read_bytes() == b"line1\nline2\n"`.
  Update the docstring.
- **New, in `test_line_endings_file_tools.py`:**
  - Overwriting an existing LF / CRLF / CR file keeps its style (parametrize).
  - CRLF content saved onto an existing LF file → LF on disk.
  - Mixed target → majority ending; a tie → platform default (monkeypatched both ways).
  - New file:
    - in a `git.Repo.init(project_dir)` repo with `.gitattributes` `*.sh eol=lf` / `*.bat eol=crlf`
      → those endings, with the platform default monkeypatched to the opposite;
    - with no repo → platform default.
  - An existing empty file, and one with no line breaks, follow the `eol=` rule.
  - The lookup is not called when the target has line breaks.
  - Overwriting an existing non-UTF-8 file (`b"\xff\xfe\x00bad\n"`) succeeds and writes the new
    content.
