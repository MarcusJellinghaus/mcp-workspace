"""Tests for the full-read line limit (max_lines) in file operations."""

from pathlib import Path

import pytest

from mcp_workspace.file_tools.file_operations import (
    DEFAULT_READ_MAX_LINES,
    append_file,
    read_file,
)
from tests.conftest import TEST_FILE


def _write_multiline_file(project_dir: Path, lines: int = 10) -> Path:
    """Helper: create a file with numbered lines."""
    abs_path = project_dir / TEST_FILE
    content = "".join(f"line {i}\n" for i in range(1, lines + 1))
    abs_path.write_text(content, encoding="utf-8")
    return abs_path


def _lines(first: int, last: int) -> str:
    """Helper: the content of lines *first*..*last* as written by the helper."""
    return "".join(f"line {i}\n" for i in range(first, last + 1))


@pytest.mark.parametrize(
    ("total", "limit", "next_end"),
    [
        (7, 5, 7),  # 2N > total → end_line clamps to total
        (25, 5, 10),  # 2N < total → end_line is 2N
    ],
)
def test_read_file_max_lines_truncates(
    project_dir: Path, total: int, limit: int, next_end: int
) -> None:
    """A full read beyond the limit returns N lines plus the paging note."""
    _write_multiline_file(project_dir, lines=total)
    content = read_file(str(TEST_FILE), project_dir, max_lines=limit)
    assert content == _lines(1, limit) + (
        f"[truncated: showing lines 1–{limit} of {total}; "
        f"continue with start_line={limit + 1}, end_line={next_end}]"
    )


@pytest.mark.parametrize("total", [5, 3])
def test_read_file_max_lines_not_exceeded(project_dir: Path, total: int) -> None:
    """A file with at most N lines is returned unchanged, without a note."""
    abs_path = _write_multiline_file(project_dir, lines=total)
    content = read_file(str(TEST_FILE), project_dir, max_lines=5)
    assert content == abs_path.read_text(encoding="utf-8")
    assert "[truncated" not in content


@pytest.mark.parametrize("max_lines", [None, 0])
def test_read_file_max_lines_disabled(project_dir: Path, max_lines: int | None) -> None:
    """max_lines None or 0 means no limit."""
    abs_path = _write_multiline_file(project_dir, lines=50)
    content = read_file(str(TEST_FILE), project_dir, max_lines=max_lines)
    assert content == abs_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("max_lines", [-1, True, "5"])
@pytest.mark.parametrize("line_range", [(None, None), (1, 3)])
def test_read_file_max_lines_invalid(
    project_dir: Path, max_lines: object, line_range: tuple[int | None, int | None]
) -> None:
    """Negative, bool and non-int max_lines raise, with or without a range."""
    _write_multiline_file(project_dir)
    start_line, end_line = line_range
    with pytest.raises(ValueError):
        read_file(
            str(TEST_FILE),
            project_dir,
            start_line=start_line,
            end_line=end_line,
            max_lines=max_lines,  # type: ignore[arg-type]
        )


def test_read_file_max_lines_ignored_for_range(project_dir: Path) -> None:
    """An explicit range larger than the limit is returned in full."""
    _write_multiline_file(project_dir, lines=20)
    content = read_file(
        str(TEST_FILE),
        project_dir,
        start_line=1,
        end_line=15,
        with_line_numbers=False,
        max_lines=5,
    )
    assert content == _lines(1, 15)


def test_read_file_max_lines_with_line_numbers(project_dir: Path) -> None:
    """Only the N content lines are numbered; the note is not."""
    _write_multiline_file(project_dir, lines=12)
    content = read_file(
        str(TEST_FILE), project_dir, with_line_numbers=True, max_lines=10
    )
    numbered = "".join(f"{i:>2}→line {i}\n" for i in range(1, 11))
    assert content == numbered + (
        "[truncated: showing lines 1–10 of 12; "
        "continue with start_line=11, end_line=12]"
    )


def test_read_file_max_lines_crlf(project_dir: Path) -> None:
    """CRLF lines are counted correctly and the note starts on its own line."""
    abs_path = project_dir / TEST_FILE
    abs_path.write_bytes("".join(f"line {i}\r\n" for i in range(1, 8)).encode())
    content = read_file(str(TEST_FILE), project_dir, max_lines=3)
    assert content == _lines(1, 3) + (
        "[truncated: showing lines 1–3 of 7; continue with start_line=4, end_line=6]"
    )


def test_append_file_not_limited(project_dir: Path) -> None:
    """append_file keeps the whole file even beyond DEFAULT_READ_MAX_LINES."""
    abs_path = _write_multiline_file(project_dir, lines=DEFAULT_READ_MAX_LINES + 10)
    original = abs_path.read_text(encoding="utf-8")
    assert append_file(str(TEST_FILE), "appended\n", project_dir=project_dir) is True
    assert abs_path.read_text(encoding="utf-8") == original + "appended\n"


def test_default_read_max_lines_exported() -> None:
    """DEFAULT_READ_MAX_LINES is re-exported from the file_tools package."""
    from mcp_workspace.file_tools import (  # pylint: disable=import-outside-toplevel
        DEFAULT_READ_MAX_LINES as exported,
    )

    assert exported == 2000
