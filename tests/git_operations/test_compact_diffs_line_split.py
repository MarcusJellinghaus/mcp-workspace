"""Tests for compact_diffs.py — diff lines are split on newlines only."""

import pytest

from mcp_workspace.git_operations.compact_diffs import (
    Hunk,
    parse_diff,
    render_compact_diff,
    render_hunk,
)

# Characters str.splitlines() treats as line boundaries that are diff line content.
_SEPARATORS = [
    "\x0b",
    "\x0c",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x85",
    "\N{LINE SEPARATOR}",
    "\N{PARAGRAPH SEPARATOR}",
]


def _diff(*hunk_lines: str) -> str:
    r"""One-file, one-hunk diff with hunk_lines joined by \n (no trailing newline)."""
    return (
        "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1,3 +1,3 @@\n"
        + "\n".join(hunk_lines)
    )


class TestSplitDiffLines:
    r"""Separators other than \n / \r\n stay inside their diff line."""

    @pytest.mark.parametrize("prefix", ["+", "-", " "])
    @pytest.mark.parametrize("sep", _SEPARATORS)
    def test_separator_terminated_line_followed_by_line(
        self, sep: str, prefix: str
    ) -> None:
        result = render_compact_diff(_diff(prefix + sep, " tail"), "")
        assert result.split("\n")[-2:] == [prefix + sep, " tail"]

    @pytest.mark.parametrize("line", ["+foo\x0c", "+foo\r\r"])
    def test_other_separator_terminated_lines(self, line: str) -> None:
        result = render_compact_diff(_diff(line, " tail"), "")
        assert result.split("\n")[-1] == " tail"

    @pytest.mark.parametrize("line", ["+x = 1\x0c-fake", "+x\r-fake"])
    def test_mid_line_separator_not_split(self, line: str) -> None:
        lines = render_compact_diff(_diff(line, " tail"), "").split("\n")
        assert line in lines
        assert "-fake" not in lines

    def test_trailing_newline_adds_no_empty_line(self) -> None:
        assert parse_diff(_diff("+a", " b") + "\n")[0].hunks[0].lines == ["+a", " b"]

    def test_crlf_carriage_return_stripped(self) -> None:
        lines = render_compact_diff(_diff("+a\r", " b\r", ""), "").split("\n")
        assert "+a" in lines
        assert " b" in lines
        assert not any(line.endswith("\r") for line in lines)


class TestRenderHunkEmptyLine:
    """Empty hunk lines (e.g. diff.suppressBlankEmpty) render as context."""

    def test_empty_line_rendered_as_context(self) -> None:
        hunk = Hunk(header="@@ -1,3 +1,3 @@", lines=[" a", "", " b"])
        assert render_hunk(hunk, set()) == "@@ -1,3 +1,3 @@\n a\n\n b"
