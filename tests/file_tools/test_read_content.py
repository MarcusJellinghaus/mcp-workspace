"""Tests for read_content / decode_lines: the read line loop on bytes."""

from pathlib import Path
from typing import Any

import pytest

from mcp_workspace.file_tools.file_operations import (
    decode_lines,
    read_content,
    read_file,
)

CONTENTS = [
    pytest.param(b"a\nb\nc\n", id="lf"),
    pytest.param(b"a\r\nb\r\nc", id="crlf-no-final-newline"),
    pytest.param(b"a\rb\rc\r", id="cr"),
    pytest.param(b"a\x0cb\nc\n", id="form-feed"),
    pytest.param(b"a\xe2\x80\xa8b\n", id="line-separator-u2028"),
    pytest.param(b"", id="empty"),
    pytest.param(b"x\ny\nz", id="one-line-over-max-lines"),
]

READ_ARGS = [
    pytest.param({}, id="full"),
    pytest.param({"start_line": 1, "end_line": 2}, id="slice"),
    pytest.param({"start_line": 2, "end_line": 5}, id="slice-past-end"),
    pytest.param({"with_line_numbers": True}, id="line-numbers"),
    pytest.param({"max_lines": 2}, id="max-lines"),
]


def _write(tmp_path: Path, data: bytes) -> Path:
    """Helper: write *data* to ``f.txt`` under *tmp_path*."""
    path = tmp_path / "f.txt"
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("data", CONTENTS)
@pytest.mark.parametrize("kwargs", READ_ARGS)
def test_read_content_matches_read_file(
    tmp_path: Path, data: bytes, kwargs: dict[str, Any]
) -> None:
    """read_content returns exactly what read_file returns for the same bytes."""
    _write(tmp_path, data)
    expected = read_file("f.txt", tmp_path, **kwargs)
    assert read_content(data, "f.txt", **kwargs) == expected


@pytest.mark.parametrize("data", CONTENTS)
def test_decode_lines_matches_open(tmp_path: Path, data: bytes) -> None:
    """decode_lines splits like open() in text mode, not like str.splitlines()."""
    path = _write(tmp_path, data)
    with open(path, encoding="utf-8") as fh:
        expected = fh.readlines()
    assert decode_lines(data) == expected


def test_read_content_truncation_note_present() -> None:
    """A full read past max_lines carries the paging note."""
    content = read_content(b"x\ny\nz", "f.txt", max_lines=2)
    assert content == (
        "x\ny\n[truncated: showing lines 1–2 of 3; "
        "continue with start_line=3, end_line=3]"
    )


def test_read_content_invalid_utf8_raises_value_error() -> None:
    """Undecodable bytes raise read_file's ValueError, naming the path."""
    with pytest.raises(ValueError, match="contains invalid characters") as exc:
        read_content(b"\xff\xfe", "bin.dat")
    assert "bin.dat" in str(exc.value)


def test_decode_lines_invalid_utf8_raises_unicode_decode_error() -> None:
    """decode_lines lets UnicodeDecodeError propagate."""
    with pytest.raises(UnicodeDecodeError):
        decode_lines(b"\xff")


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"start_line": 3, "end_line": 1}, id="end-before-start"),
        pytest.param({"start_line": 1}, id="start-only"),
        pytest.param({"end_line": 1}, id="end-only"),
        pytest.param({"start_line": 0, "end_line": 1}, id="start-zero"),
        pytest.param({"max_lines": -1}, id="negative-max-lines"),
        pytest.param({"max_lines": True}, id="bool-max-lines"),
    ],
)
def test_read_content_invalid_args_match_read_file(
    tmp_path: Path, kwargs: dict[str, Any]
) -> None:
    """Invalid ranges and limits raise the same ValueError text as read_file."""
    _write(tmp_path, b"a\nb\nc\n")
    with pytest.raises(ValueError) as file_exc:
        read_file("f.txt", tmp_path, **kwargs)
    with pytest.raises(ValueError) as content_exc:
        read_content(b"a\nb\nc\n", "f.txt", **kwargs)
    assert str(content_exc.value) == str(file_exc.value)


def test_read_content_empty_file_path_rejected() -> None:
    """file_path is validated like read_file's."""
    with pytest.raises(ValueError, match="non-empty string"):
        read_content(b"a\n", "")
