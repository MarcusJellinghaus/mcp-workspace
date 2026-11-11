# Step 3 — `edit_file` keeps line endings

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md`: make `edit_file`
> write in the file's own line-ending style using `target_newline` from step 2. Write and rewrite
> the tests first. Run pylint, pytest (`-n auto`) and mypy, all green. Run `run_format_code`, then
> make one commit.

## WHERE

- `src/mcp_workspace/file_tools/edit_file.py`
- `src/mcp_workspace/toolset/write.py` — `edit_file` tool docstring
- `tests/file_tools/test_edit_file.py` — rewrite `test_crlf_normalization` (`:192`)
- `tests/file_tools/test_line_endings_file_tools.py` — new (shared with steps 4–5)

## WHAT

```python
def _write_file(path: Path, content: str, newline: str) -> None:
    """Write LF-normalised content, translating each \\n to newline."""
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(content)
```

`edit_file` keeps its signature.

## HOW

- Resolve `rel_path`: `abs_path, rel_path = normalize_path(...)` when `project_dir` is set;
  otherwise `rel_path = file_path`. Without `project_dir` the `eol=` lookup is skipped, because
  `target_newline` returns the platform default for `project_dir=None`.
- Replace the text-mode read (`:54-55`) with:
  `raw = abs_path.read_bytes()`, then `original_content = normalize_line_endings(raw.decode("utf-8"))`.
  A non-UTF-8 file still raises `UnicodeDecodeError`, as today.
- At both write sites (empty `old_string` prepend, and replacement):
  `_write_file(abs_path, modified_content, target_newline(raw, rel_path, project_dir))`.
  Work out the ending only there, so the "already applied" returns never call git.
- `_create_diff` stays on the LF strings, so the returned diff is LF.
- Docstring (util and tool): "Line endings: an existing file keeps its style (mixed → most common,
  tie → platform default); a file with no line breaks follows .gitattributes eol=, else the
  platform default. Matching and the returned diff use LF."

## ALGORITHM

```
raw = abs_path.read_bytes()
original = normalize_line_endings(raw.decode("utf-8"))
... unchanged matching logic ...
on write: _write_file(abs_path, modified, target_newline(raw, rel_path, project_dir))
```

## Tests

- **Rewrite `test_crlf_normalization`:** the CRLF file is edited and
  `read_bytes() == b"hi\r\nworld\r\n"`. Update the docstring.
- **New, in `test_line_endings_file_tools.py`** (use `project_dir`, assert `read_bytes()`):
  - LF, CRLF and CR files each keep their style after an edit, multi-line `new_string` included
    (parametrize).
  - A mixed file (2× CRLF, 1× LF) → all CRLF.
  - A tie → `PLATFORM_NEWLINE`, monkeypatched to `"\n"` and to `"\r\n"`.
  - A file with no line breaks + `new_string` containing `\n`: the ending comes from a patched
    `mcp_workspace.git_operations.get_eol_attribute` (`"lf"` → `\n`, `"crlf"` → `\r\n`).
  - An empty existing file: an empty `old_string` prepends a `new_string` containing `\n`; the
    ending comes from the patched `get_eol_attribute` the same way (`"lf"` → `\n`,
    `"crlf"` → `\r\n`).
  - The lookup is not called for a file with line breaks.
  - The returned diff has no `\r` on a CRLF file.
  - An "already applied" edit on a CRLF file leaves the bytes identical.
