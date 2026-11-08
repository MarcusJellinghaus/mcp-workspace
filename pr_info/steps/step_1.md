# Step 1 — Shared `read_file` gets `max_lines`; export `DEFAULT_READ_MAX_LINES`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 1** exactly as described in `pr_info/steps/step_1.md`. Write the tests first, then the implementation. Run pylint, pytest (`-n auto`) and mypy via the MCP tools; all must pass. Run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/file_tools/file_operations.py`
- `src/mcp_workspace/file_tools/__init__.py`
- `tests/file_tools/test_file_operations.py`

## WHAT

```python
# file_operations.py (module level, near logger)
DEFAULT_READ_MAX_LINES = 2000

def read_file(
    file_path: str,
    project_dir: Path,
    start_line: int | None = None,
    end_line: int | None = None,
    with_line_numbers: bool | None = None,
    max_lines: int | None = None,
) -> str: ...
```

`__init__.py`: import `DEFAULT_READ_MAX_LINES` from `file_operations` and add it to `__all__`.

`append_file` is **not** changed — it keeps calling `read_file(file_path, project_dir)` (no limit).

## HOW

- Validation of `max_lines` goes right after the `project_dir` check and **before** the line-range checks:
  - `isinstance(max_lines, bool) or not isinstance(max_lines, int)` (when not `None`) → `ValueError`
  - `max_lines < 0` → `ValueError`
- Effective limit: `limit = max_lines or None` if `start_line is None`, else `None` (range reads ignore it).
- Extend the existing read loop; do not extract a helper unless pylint complains.
- Docstring: document `max_lines` and the `ValueError`.

## ALGORITHM

```
limit = max_lines if (start_line is None and max_lines) else None
for line_num, line in enumerate(fh, 1):
    if limit is not None and line_num > limit: total = line_num; continue   # count only
    (existing collect / end_line break logic)
build content from collected (existing numbering; width from last collected = N)
if limit is not None and total > limit:
    content += f"[truncated: showing lines 1–{limit} of {total}; continue with start_line={limit + 1}, end_line={min(2 * limit, total)}]"
```

(`–` is U+2013. Initialise `total = 0`. Truncation only occurs when line N+1 exists, so line N ends with `\n`.)

## DATA

- Returns `str`. Untruncated output is byte-identical to today.
- Truncated output: first N lines (optionally numbered) + note, no trailing newline after the note.

## Tests (write first) — `tests/file_tools/test_file_operations.py`

- File with N+k lines, `max_lines=N` → first N lines + exact note (check total and `end_line=min(2N, total)`; one case where `2N > total`, one where `2N < total`).
- File with exactly N lines and with fewer → returned unchanged, no note.
- `max_lines=None` and `max_lines=0` → full file.
- Parametrized invalid: `-1`, `True`, `"5"` → `ValueError`, also when `start_line`/`end_line` is given.
- Range larger than the limit (`start_line=1, end_line=3N`, `max_lines=N`) → all requested lines returned, no note.
- `with_line_numbers=True` on a truncated read → N numbered lines, note unnumbered.
- `\r\n` file truncated → total counts lines correctly, note on its own line.
- `append_file` on a file with more than `DEFAULT_READ_MAX_LINES` lines → full original content preserved plus appended text.
- `from mcp_workspace.file_tools import DEFAULT_READ_MAX_LINES` equals `2000`.
