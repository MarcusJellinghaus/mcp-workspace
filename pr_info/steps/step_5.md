# Step 5 — `append_file` becomes a real append in the file's ending

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md`: replace
> `append_file`'s read-and-rewrite with a real `"a"` append in the file's line-ending style.
> Write and rewrite the tests first. Run pylint, pytest (`-n auto`) and mypy, all green. Run
> `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/file_tools/file_operations.py` — `append_file` (`:355-363`)
- `src/mcp_workspace/toolset/write.py` — `append_file` tool docstring
- `tests/file_tools/test_file_operations.py` — rewrite `test_append_file_normalizes_crlf` (`:603`)
- `tests/file_tools/test_line_endings_file_tools.py` — add tests

## WHAT

`append_file(file_path, content, project_dir) -> bool`, with the signature unchanged.

## HOW

- The validation and the `FileNotFoundError` / `IsADirectoryError` checks stay as they are.
- Replace the `read_file` + `save_file` lines with an append. Wrap `UnicodeEncodeError` in the
  same `ValueError` message that `_write_file_atomically` uses.
- No newline is inserted before the appended text. The append is not atomic (accepted in the
  issue).
- Docstring (util and tool): "Appends without touching existing bytes; the appended text uses the
  file's line ending (no line breaks → .gitattributes eol=, else platform default). No newline is
  inserted before it."

## ALGORITHM

```
abs_path, rel_path, content = _validate_save_parameters(...)
<existing exists / is_file checks>
newline = target_newline(abs_path.read_bytes(), rel_path, project_dir)
with open(abs_path, "a", encoding="utf-8", newline=newline) as f:
    f.write(content)          # UnicodeEncodeError -> ValueError (same message as save)
return True
```

## Tests

- **Rewrite `test_append_file_normalizes_crlf`:** seed the file with `write_bytes(b"existing\n")`,
  not `write_text("existing\n")`, which writes CRLF on Windows. Appending CRLF content →
  `read_bytes() == b"existing\nnew\nline\n"`. Update the docstring.
- **New, in `test_line_endings_file_tools.py`:**
  - LF / CRLF / CR files: the existing bytes are an unchanged prefix, and the appended part uses
    the file's ending (parametrize).
  - A mixed file: the existing bytes are untouched (including the minority endings); the appended
    part uses the majority ending.
  - A file without a trailing newline (`b"a\r\nb"`) + `"c\n"` → `b"a\r\nbc\r\n"` (no newline
    inserted).
  - An empty / no-line-break file → `eol=` rule (patched `get_eol_attribute`), else platform
    default.
  - The lookup is not called when the file has line breaks.
  - Appending to a non-UTF-8 file succeeds, and the existing bytes are untouched.
  - A missing file still raises `FileNotFoundError`.
