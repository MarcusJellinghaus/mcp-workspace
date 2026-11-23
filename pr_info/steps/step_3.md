# Step 3 — `read_content` / `decode_lines`: the read line loop on bytes

No behaviour change for `read_file`.

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_3.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy; all must pass. Run
> `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/file_tools/file_operations.py`
- `tests/file_tools/test_read_content.py` (new)

## WHAT

```python
def _validate_read_args(
    file_path: str, start_line: int | None, end_line: int | None, max_lines: int | None
) -> None: ...          # today's checks from read_file, moved verbatim

def _render_lines(
    lines: Iterable[str], start_line: int | None, end_line: int | None,
    with_line_numbers: bool | None, max_lines: int | None,
) -> str: ...           # today's loop + numbering + truncation note, moved verbatim

def read_content(
    data: bytes, file_path: str, start_line: int | None = None, end_line: int | None = None,
    with_line_numbers: bool | None = None, max_lines: int | None = None,
) -> str: ...           # file_path is used only in messages

def decode_lines(data: bytes) -> list[str]: ...
```

## HOW

- `read_file` calls `_validate_read_args`, keeps its path / exists / is-file checks, then
  `with open(abs_path, encoding="utf-8") as fh: content = _render_lines(fh, …)` inside its
  existing `try` (the context manager stays, so the handle is closed at once — Windows file
  locks), so its error handling (UnicodeDecodeError → today's ValueError text) is unchanged.
- `read_content` and `decode_lines` decode with
  `io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")` — the same universal-newline
  semantics as `open()`. Never `str.splitlines()` (see #410).
- Not exported from `file_tools/__init__.py` (callers import from `file_operations`); no
  GitPython import.

## ALGORITHM (read_content)

```
_validate_read_args(file_path, start_line, end_line, max_lines)
stream = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
try: return _render_lines(stream, start_line, end_line, with_line_numbers, max_lines)
except UnicodeDecodeError as e:
    raise ValueError(f"File '{file_path}' contains invalid characters. Ensure it's a valid text file.") from e
```

`decode_lines`: `return io.TextIOWrapper(io.BytesIO(data), encoding="utf-8").readlines()`
(lets `UnicodeDecodeError` propagate — search treats it as a silent skip).

## DATA

`read_content` returns exactly what `read_file` would return for a file with these bytes.

## Tests (write first)

Parametrise over contents `b"a\nb\nc\n"`, `b"a\r\nb\r\nc"`, `b"a\rb\rc\r"`, `b"a\x0cb\nc\n"`,
`b"a\xe2\x80\xa8b\n"` (U+2028), empty, and one line longer than `max_lines`:
- Write the bytes to a file; `read_content(data, "f.txt", …) == read_file("f.txt", tmp, …)`
  for: full read, `start_line/end_line` slice, `with_line_numbers=True`, and `max_lines=2`
  (truncation note identical).
- `decode_lines(data) == open(path, encoding="utf-8").readlines()` for the same bytes.
- `read_content(b"\xff\xfe", "bin.dat")` raises `ValueError` matching "contains invalid characters".
- `decode_lines(b"\xff")` raises `UnicodeDecodeError`.
- Invalid ranges (`start_line=3, end_line=1`, only one of the two, `max_lines=-1`) raise the
  same `ValueError` texts as `read_file`.
