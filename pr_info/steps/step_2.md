# Step 2 — `edit_file` and `append_file` write via `fs.write_text`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md` exactly.
> TDD: add the two tests first and run them (the `edit_file` test fails today —
> the file is emptied), then change the code. Use the MCP tools only. Run the
> checks below; all must pass. Then run `run_format_code` and make exactly one commit.

## Tests first — `tests/file_tools/test_line_endings_file_tools.py`

Append at the end (lone surrogate cannot be encoded to UTF-8):

```python
def test_append_file_unencodable_content_keeps_bytes(tmp_path: Path) -> None:
    """Unencodable content raises the encoding ValueError; the file is untouched."""
    original = b"a\nb\n"
    (tmp_path / "f.txt").write_bytes(original)

    with pytest.raises(ValueError, match="cannot be encoded"):
        append_file("f.txt", "x\ud800", project_dir=tmp_path)

    assert (tmp_path / "f.txt").read_bytes() == original


def test_edit_file_unencodable_content_keeps_bytes(tmp_path: Path) -> None:
    """Unencodable new_string raises UnicodeEncodeError; the file is untouched."""
    original = b"a\nb\n"
    (tmp_path / "f.txt").write_bytes(original)

    with pytest.raises(UnicodeEncodeError):
        edit_file("f.txt", "b", "\ud800", project_dir=tmp_path)

    assert (tmp_path / "f.txt").read_bytes() == original
```

The file has a dominant LF ending, so no git lookup runs; no patch needed.

## WHERE / WHAT / HOW

### `src/mcp_workspace/file_tools/edit_file.py`
- Import `write_text` alongside `normalize_line_endings` from `mcp_coder_utils.fs`.
- Delete `_write_file`.
- Both former call sites become:
  ```python
  write_text(abs_path, modified_content, newline=target_newline(raw, rel_path, project_dir))
  ```
- No `try` / wrap: `UnicodeEncodeError` propagates as today.

### `src/mcp_workspace/file_tools/file_operations.py` — `append_file`
- Import `write_text` from `mcp_coder_utils.fs`.
- Keep the `exists()` / `is_file()` checks before the write (`write_text(append=True)`
  would create a missing file — `test_append_file_missing_file_raises`).
- Replace the `with open(..., "a", ...)` block:

## ALGORITHM (`append_file` tail)

```
newline = target_newline(abs_path.read_bytes(), rel_path, project_dir)
log debug "Appending ..."
try: write_text(abs_path, validated_content, newline=newline, append=True)
except UnicodeEncodeError as e:            # only this; ValueError for a bad newline must not be relabelled
    log error; raise ValueError("Content contains characters that cannot be encoded. Please check the encoding.") from e
return True
```

`save_file` and `_write_file_atomically` are unchanged.

## DATA

`edit_file(...) -> str` (diff) and `append_file(...) -> bool` unchanged.

## Checks

`run_pylint_check`, `run_pytest_check(extra_args=["-n", "auto"])`, `run_mypy_check`,
`run_ruff_check`, `run_tach_check`, `run_lint_imports_check`, `run_vulture_check`.

## Commit

`refactor(file_tools): write edit_file and append_file via mcp_coder_utils.fs.write_text`

Body: note that `edit_file` with unencodable content no longer empties the file.
