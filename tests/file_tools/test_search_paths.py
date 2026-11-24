"""Tests for search_paths: the search engine on an injected file list and reader."""

import sys
from collections.abc import Callable

import pytest

from mcp_workspace.file_tools.search import search_paths


def _reader(contents: dict[str, list[str]]) -> Callable[[str], list[str]]:
    """Build an in-memory reader over a ``{path: lines}`` mapping.

    Returns:
        A ``read_lines`` callable returning the stored lines for a path.
    """

    def read_lines(path: str) -> list[str]:
        return contents[path]

    return read_lines


def _failing_reader(
    contents: dict[str, list[str]], failures: dict[str, Exception]
) -> Callable[[str], list[str]]:
    """Build an in-memory reader that raises for selected paths.

    Returns:
        A ``read_lines`` callable raising ``failures[path]`` when present.
    """

    def read_lines(path: str) -> list[str]:
        if path in failures:
            raise failures[path]
        return contents[path]

    return read_lines


@pytest.fixture
def win32(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make spec builds take the win32 (case-insensitive) branch."""
    monkeypatch.setattr(sys, "platform", "win32")


class TestSearchPathsArgs:
    """Argument validation."""

    def test_no_glob_no_pattern_raises(self) -> None:
        """Neither glob nor pattern provided raises ValueError."""
        with pytest.raises(ValueError, match="At least one of 'glob' or 'pattern'"):
            search_paths(["a.py"], _reader({"a.py": []}))


class TestSearchPathsOrder:
    """The given file order is kept."""

    def test_file_search_keeps_order(self) -> None:
        """File-search results follow the order of ``files``."""
        files = ["b/x.py", "a.py"]
        result = search_paths(files, _reader({}), glob="*.py")

        assert result["mode"] == "file_search"
        assert result["files"] == ["b/x.py", "a.py"]
        assert result["total_files"] == 2
        assert result["truncated"] is False

    def test_content_search_keeps_order(self) -> None:
        """Content-search details follow the order of ``files``."""
        contents = {"b/x.py": ["hit\n"], "a.py": ["hit\n"]}
        result = search_paths(["b/x.py", "a.py"], _reader(contents), pattern="hit")

        assert result["mode"] == "content_search"
        assert [m["file"] for m in result["details"]] == ["b/x.py", "a.py"]
        assert result["total_matches"] == 2

    def test_content_search_without_glob_searches_all_files(self) -> None:
        """Without a glob every given file is read."""
        contents = {"a.txt": ["x\n"], "b.md": ["x\n"]}
        result = search_paths(["a.txt", "b.md"], _reader(contents), pattern="x")

        assert {m["file"] for m in result["details"]} == {"a.txt", "b.md"}


class TestSearchPathsReaderErrors:
    """Reader failures are skipped or reported as today."""

    @pytest.mark.parametrize(
        "error",
        [
            pytest.param(OSError("boom"), id="oserror"),
            pytest.param(ValueError("bad path"), id="valueerror"),
        ],
    )
    def test_reader_error_reported_as_skipped(self, error: Exception) -> None:
        """A failing path lands in ``skipped_files``; others are still searched."""
        contents = {"good.py": ["def target():\n"], "bad.py": ["def target():\n"]}
        reader = _failing_reader(contents, {"bad.py": error})

        result = search_paths(["bad.py", "good.py"], reader, pattern="def target")

        assert [m["file"] for m in result["details"]] == ["good.py"]
        assert result["skipped_files"] == ["bad.py"]

    def test_unicode_decode_error_silently_skipped(self) -> None:
        """A path whose content cannot be decoded is skipped silently."""
        contents = {"text.py": ["def hello():\n"]}
        error = UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")
        reader = _failing_reader(contents, {"binary.bin": error})

        result = search_paths(["binary.bin", "text.py"], reader, pattern="def hello")

        assert [m["file"] for m in result["details"]] == ["text.py"]
        assert "skipped_files" not in result

    def test_file_search_does_not_call_reader(self) -> None:
        """Glob-only mode never reads content."""

        def read_lines(path: str) -> list[str]:
            raise AssertionError(f"unexpected read of {path}")

        result = search_paths(["a.py"], read_lines, glob="*.py")

        assert result["files"] == ["a.py"]


class TestSearchPathsGlob:
    """Glob handling matches search_files."""

    def test_brace_glob_without_match_has_glob_note(self) -> None:
        """A brace glob matching nothing carries ``glob_note``."""
        result = search_paths(["a.py"], _reader({}), glob="{a,b}.py")

        assert result["total_files"] == 0
        assert "brace expansion" in result["glob_note"].lower()

    def test_brace_glob_note_in_content_search(self) -> None:
        """The glob note is attached in content-search mode too."""
        result = search_paths(
            ["a.py"], _reader({"a.py": ["x\n"]}), glob="{a,b}.py", pattern="x"
        )

        assert result["mode"] == "content_search"
        assert "brace expansion" in result["glob_note"].lower()

    @pytest.mark.parametrize("glob", ["", "#*.py", "!*.py", "["])
    def test_unparseable_glob_raises(self, glob: str) -> None:
        """A glob that matches nothing by construction raises ValueError."""
        with pytest.raises(ValueError, match="matches nothing by construction"):
            search_paths(["a.py"], _reader({}), glob=glob)

    @pytest.mark.usefixtures("win32")
    def test_win32_glob_case_insensitive(self) -> None:
        """On win32, ``**/CLAUDE.md`` matches ``Claude.md``."""
        result = search_paths(
            ["Claude.md", "other.md"], _reader({}), glob="**/CLAUDE.md"
        )

        assert result["files"] == ["Claude.md"]

    def test_file_search_max_results_truncates(self) -> None:
        """File search caps at ``max_results`` and flags truncation."""
        files = [f"f{i}.dat" for i in range(10)]
        result = search_paths(files, _reader({}), glob="*.dat", max_results=3)

        assert result["files"] == ["f0.dat", "f1.dat", "f2.dat"]
        assert result["total_files"] == 10
        assert result["truncated"] is True


class TestSearchPathsContent:
    """Content search behaviour matches search_files."""

    def test_invalid_regex_falls_back_to_literal(self) -> None:
        """An invalid regex is searched literally, with a note."""
        contents = {"code.py": ["def hello(world):\n", "    pass\n"]}
        result = search_paths(["code.py"], _reader(contents), pattern="hello(")

        assert result["total_matches"] == 1
        assert "hello(" in result["details"][0]["text"]
        assert "literal" in result["note"].lower()

    def test_valid_regex_has_no_note(self) -> None:
        """A valid regex carries no note."""
        contents = {"code.py": ["def hello():\n"]}
        result = search_paths(["code.py"], _reader(contents), pattern=r"def \w+")

        assert "note" not in result

    def test_context_lines(self) -> None:
        """Surrounding lines are included with ``context_lines``."""
        lines = ["line1\n", "line2\n", "MATCH_HERE\n", "line4\n", "line5\n"]
        result = search_paths(
            ["ctx.py"],
            _reader({"ctx.py": lines}),
            pattern="MATCH_HERE",
            context_lines=1,
        )

        match = result["details"][0]
        assert match["line"] == 3
        assert match["text"] == "line2\nMATCH_HERE\nline4"

    def test_max_results_truncation(self) -> None:
        """Content search caps details at ``max_results``."""
        lines = [f"hit {i}\n" for i in range(5)]
        result = search_paths(
            ["a.txt"], _reader({"a.txt": lines}), pattern="hit", max_results=2
        )

        assert len(result["details"]) == 2
        assert result["total_matches"] == 5
        assert result["truncated"] is True
        assert result["matched_files"] == [{"file": "a.txt", "lines": [1, 2, 3, 4, 5]}]

    def test_char_budget_truncation(self) -> None:
        """``max_result_lines * 120`` chars caps the returned text."""
        lines = [f"match_line_{i}\n" for i in range(20)]
        result = search_paths(
            ["many.txt"],
            _reader({"many.txt": lines}),
            pattern="match_line_",
            max_results=100,
            max_result_lines=1,
        )

        assert result["truncated"] is True
        assert sum(len(m["text"]) for m in result["details"]) <= 120
        assert result["total_matches"] == 20
        assert "matched_files" in result

    def test_not_truncated_has_no_matched_files(self) -> None:
        """Without truncation, ``matched_files`` is absent."""
        result = search_paths(
            ["s.txt"], _reader({"s.txt": ["hello\n"]}), pattern="hello"
        )

        assert result["truncated"] is False
        assert "matched_files" not in result
