"""Tests for search_files glob-only, content search, and combined modes."""

import sys
from pathlib import Path

import pytest

from mcp_workspace.file_tools.search import search_files


class TestSearchFilesGlobOnly:
    """Tests for file search (glob-only) mode."""

    def test_search_files_no_args_raises(self, project_dir: Path) -> None:
        """Neither glob nor pattern provided raises ValueError."""
        with pytest.raises(ValueError, match="At least one of 'glob' or 'pattern'"):
            search_files(project_dir)

    def test_search_files_glob_finds_files(self, project_dir: Path) -> None:
        """Glob pattern matches only the expected file types."""
        search_dir = project_dir / "search_test"
        search_dir.mkdir()
        (search_dir / "app.py").write_text("print('hello')")
        (search_dir / "utils.py").write_text("x = 1")
        (search_dir / "readme.txt").write_text("docs")

        result = search_files(project_dir, glob="**/*.py")

        assert result["mode"] == "file_search"
        assert result["truncated"] is False
        matched = result["files"]
        # Our created .py files should be in the results
        matched_basenames = {Path(f).name for f in matched}
        assert "app.py" in matched_basenames
        assert "utils.py" in matched_basenames
        assert "readme.txt" not in matched_basenames

    def test_search_files_glob_no_matches(self, project_dir: Path) -> None:
        """Glob that matches nothing returns empty files list."""
        result = search_files(project_dir, glob="**/*.nonexistent_extension_xyz")

        assert result["mode"] == "file_search"
        assert result["files"] == []
        assert result["total_files"] == 0
        assert result["truncated"] is False

    def test_search_files_glob_max_results(self, project_dir: Path) -> None:
        """Verify max_results truncation and truncated flag."""
        bulk_dir = project_dir / "bulk"
        bulk_dir.mkdir()
        for i in range(10):
            (bulk_dir / f"file_{i}.dat").write_text(f"data {i}")

        result = search_files(project_dir, glob="**/*.dat", max_results=3)

        assert result["mode"] == "file_search"
        assert len(result["files"]) == 3
        assert result["total_files"] == 10
        assert result["truncated"] is True

    def test_double_star_matches_root_file(self, project_dir: Path) -> None:
        """``**/foo.bat`` matches a root-level file (the original bug)."""
        (project_dir / "foo.bat").write_text("@echo off\n")

        result = search_files(project_dir, glob="**/foo.bat")

        assert result["mode"] == "file_search"
        matched_basenames = {Path(f).name for f in result["files"]}
        assert "foo.bat" in matched_basenames

    def test_bare_pattern_matches_at_any_depth(self, project_dir: Path) -> None:
        """``*.py`` matches .py files at root and nested directories."""
        (project_dir / "a.py").write_text("x = 1\n")
        sub = project_dir / "sub"
        sub.mkdir()
        (sub / "b.py").write_text("y = 2\n")

        result = search_files(project_dir, glob="*.py")

        matched_basenames = {Path(f).name for f in result["files"]}
        assert "a.py" in matched_basenames
        assert "b.py" in matched_basenames

    def test_leading_slash_anchors_to_root(self, project_dir: Path) -> None:
        """``/foo.py`` anchors to project root and excludes nested files."""
        (project_dir / "foo.py").write_text("x = 1\n")
        sub = project_dir / "sub"
        sub.mkdir()
        (sub / "foo.py").write_text("y = 2\n")

        result = search_files(project_dir, glob="/foo.py")

        # Only the root foo.py should match, not sub/foo.py
        assert len(result["files"]) == 1
        matched = result["files"][0]
        assert Path(matched).name == "foo.py"
        assert "sub" not in Path(matched).parts

    def test_star_does_not_cross_path_separator(self, project_dir: Path) -> None:
        """In an anchored pattern, ``*`` matches one segment only — not across ``/``."""
        a = project_dir / "a"
        a.mkdir()
        (a / "bfoo.py").write_text("y = 2\n")
        nested = a / "x"
        nested.mkdir()
        (nested / "bfoo.py").write_text("z = 3\n")

        # Anchored pattern: 'a/*foo.py' matches 'a/<one-segment>foo.py' only.
        # Under fnmatch, '*' matched across '/' so 'a/x/bfoo.py' would also match.
        result = search_files(project_dir, glob="a/*foo.py")

        matched_paths = result["files"]
        # 'a/bfoo.py' should match (single segment after 'a/').
        assert any(
            Path(f).name == "bfoo.py" and "x" not in Path(f).parts
            for f in matched_paths
        )
        # 'a/x/bfoo.py' should NOT match — '*' must not cross '/'.
        assert not any("x" in Path(f).parts for f in matched_paths)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_windows_case_insensitive_match_preserved(self, project_dir: Path) -> None:
        """On Windows, ``README.md`` matches ``readme.md`` (case-insensitive)."""
        (project_dir / "readme.md").write_text("# docs\n")

        result = search_files(project_dir, glob="README.md")

        matched_basenames = {Path(f).name.lower() for f in result["files"]}
        assert "readme.md" in matched_basenames

    def test_search_files_glob_respects_gitignore(self, project_dir: Path) -> None:
        """Files matching .gitignore patterns are excluded."""
        (project_dir / ".gitignore").write_text("*.log\n")
        log_dir = project_dir / "logs"
        log_dir.mkdir()
        (log_dir / "app.log").write_text("log entry")
        (log_dir / "debug.log").write_text("debug entry")
        (log_dir / "keep.txt").write_text("keep me")

        result = search_files(project_dir, glob="logs/*")

        matched_names = {Path(f).name for f in result["files"]}
        assert "keep.txt" in matched_names
        assert "app.log" not in matched_names
        assert "debug.log" not in matched_names


class TestSearchFilesGlobSemantics:
    """Pins gitignore/wildmatch glob semantics that callers rely on."""

    def test_trailing_slash_matches_files_beneath(self, project_dir: Path) -> None:
        """``src/`` matches files under the directory, not siblings of it."""
        src = project_dir / "src"
        src.mkdir()
        (src / "a.py").write_text("x = 1\n")
        (project_dir / "root.py").write_text("z = 3\n")

        result = search_files(project_dir, glob="src/")

        matched_basenames = {Path(f).name for f in result["files"]}
        assert "a.py" in matched_basenames
        assert "root.py" not in matched_basenames

    @pytest.mark.parametrize("glob", ["[!a]*.py", "[^a]*.py"])
    def test_character_class_negation(self, project_dir: Path, glob: str) -> None:
        """Both ``[!a]`` and ``[^a]`` negate the character class."""
        (project_dir / "a.py").write_text("x = 1\n")
        (project_dir / "b.py").write_text("y = 2\n")

        result = search_files(project_dir, glob=glob)

        matched_basenames = {Path(f).name for f in result["files"]}
        assert "b.py" in matched_basenames
        assert "a.py" not in matched_basenames

    def test_double_star_matches_everything_below_prefix(
        self, project_dir: Path
    ) -> None:
        """``src/**`` matches at every depth below ``src``, and nothing outside it."""
        deep = project_dir / "src" / "deep"
        deep.mkdir(parents=True)
        (project_dir / "src" / "a.py").write_text("x = 1\n")
        (deep / "b.py").write_text("y = 2\n")
        (project_dir / "root.py").write_text("z = 3\n")

        result = search_files(project_dir, glob="src/**")

        matched_basenames = {Path(f).name for f in result["files"]}
        assert "a.py" in matched_basenames
        assert "b.py" in matched_basenames
        assert "root.py" not in matched_basenames

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
    def test_glob_is_case_sensitive_on_posix(self, project_dir: Path) -> None:
        """On POSIX, ``README.md`` does not match ``readme.md``.

        Companion to ``test_windows_case_insensitive_match_preserved`` in
        ``TestSearchFilesGlobOnly``: the same glob differs by platform.
        """
        (project_dir / "readme.md").write_text("# docs\n")

        result = search_files(project_dir, glob="README.md")

        assert result["files"] == []
        assert result["total_files"] == 0


class TestSearchFilesContentSearch:
    """Tests for content search (regex) and combined modes."""

    def test_search_files_pattern_finds_content(self, project_dir: Path) -> None:
        """Regex pattern matches correct lines in files."""
        src_dir = project_dir / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("def hello():\n    return 42\n")
        (src_dir / "util.py").write_text("x = 1\ndef world():\n    pass\n")

        result = search_files(project_dir, glob="src/*.py", pattern=r"def \w+")

        assert result["mode"] == "content_search"
        assert result["truncated"] is False
        assert result["total_matches"] == 2
        texts = [m["text"] for m in result["details"]]
        assert any("def hello" in t for t in texts)
        assert any("def world" in t for t in texts)

    def test_search_files_pattern_no_matches(self, project_dir: Path) -> None:
        """Regex that matches nothing returns empty matches list."""
        (project_dir / "empty.py").write_text("x = 1\n")

        result = search_files(project_dir, pattern=r"zzz_no_match_zzz")

        assert result["mode"] == "content_search"
        assert result["details"] == []
        assert result["total_matches"] == 0
        assert result["truncated"] is False

    def test_search_files_invalid_regex_falls_back_to_literal(
        self, project_dir: Path
    ) -> None:
        """Invalid regex pattern falls back to literal search with note."""
        (project_dir / "code.py").write_text("def hello(world):\n    pass\n")
        result = search_files(project_dir, pattern="hello(")
        assert result["mode"] == "content_search"
        assert result["total_matches"] == 1
        assert "hello(" in result["details"][0]["text"]
        assert "note" in result
        assert "literal" in result["note"].lower()

    def test_search_files_valid_regex_no_note(self, project_dir: Path) -> None:
        """Valid regex pattern does not produce a note field."""
        (project_dir / "code.py").write_text("def hello():\n    pass\n")
        result = search_files(project_dir, pattern=r"def \w+")
        assert result["mode"] == "content_search"
        assert "note" not in result

    def test_search_files_invalid_regex_no_matches_still_has_note(
        self, project_dir: Path
    ) -> None:
        """Invalid regex with zero matches still returns note field."""
        (project_dir / "code.py").write_text("nothing relevant here\n")
        result = search_files(project_dir, pattern="[invalid")
        assert result["mode"] == "content_search"
        assert result["total_matches"] == 0
        assert "note" in result
        assert "literal" in result["note"].lower()

    def test_search_files_combined_mode(self, project_dir: Path) -> None:
        """Glob + pattern filters both file paths and content."""
        d = project_dir / "combo"
        d.mkdir()
        (d / "app.py").write_text("def run():\n    pass\n")
        (d / "app.txt").write_text("def run():\n    pass\n")
        (d / "lib.py").write_text("x = 1\n")

        result = search_files(project_dir, glob="**/*.py", pattern=r"def run")

        assert result["mode"] == "content_search"
        files = [m["file"] for m in result["details"]]
        assert any("app.py" in f for f in files)
        # app.txt should NOT match (glob filters it out)
        assert not any("app.txt" in f for f in files)
        # lib.py should NOT match (pattern filters it out)
        assert not any("lib.py" in f for f in files)

    def test_search_files_context_lines(self, project_dir: Path) -> None:
        """Surrounding lines included in text field with context_lines."""
        (project_dir / "ctx.py").write_text("line1\nline2\nMATCH_HERE\nline4\nline5\n")

        result = search_files(project_dir, pattern=r"MATCH_HERE", context_lines=1)

        assert len(result["details"]) == 1
        match = result["details"][0]
        assert match["line"] == 3
        assert "line2" in match["text"]
        assert "MATCH_HERE" in match["text"]
        assert "line4" in match["text"]

    def test_search_files_char_budget_truncation(self, project_dir: Path) -> None:
        """Verify char budget (max_result_lines * 120) triggers truncation."""
        lines = [f"match_line_{i}" for i in range(20)]
        (project_dir / "many.txt").write_text("\n".join(lines) + "\n")

        result = search_files(
            project_dir,
            pattern=r"match_line_",
            max_results=100,
            max_result_lines=1,  # budget = 1 * 120 = 120 chars
        )

        assert result["truncated"] is True
        total_chars = sum(len(m["text"]) for m in result["details"])
        assert total_chars <= 120
        assert result["total_matches"] == 20

    def test_search_files_skips_binary_files(self, project_dir: Path) -> None:
        """Binary file with non-UTF-8 bytes is skipped without error."""
        (project_dir / "text.py").write_text("def hello():\n    pass\n")
        (project_dir / "binary.bin").write_bytes(b"\x80\x81\x82\xff\xfe")

        result = search_files(project_dir, pattern=r"def hello")

        assert result["mode"] == "content_search"
        assert len(result["details"]) == 1
        assert "text.py" in result["details"][0]["file"]


class TestSearchFilesLineTruncation:
    """Tests for per-line truncation of long lines."""

    def test_long_line_truncated_at_500_chars(self, project_dir: Path) -> None:
        """A line exceeding 500 chars is truncated with marker."""
        long_line = "x" * 1000
        (project_dir / "long.txt").write_text(long_line + "\n")

        result = search_files(project_dir, pattern=r"x+")

        detail = result["details"][0]
        assert len(detail["text"]) < 1000
        assert "... [line truncated: showing 500 of 1000 chars]" in detail["text"]
        assert detail["text"].startswith("x" * 500)

    def test_short_line_not_truncated(self, project_dir: Path) -> None:
        """A line under 500 chars is returned as-is."""
        line = "y" * 499
        (project_dir / "short.txt").write_text(line + "\n")

        result = search_files(project_dir, pattern=r"y+")

        assert result["details"][0]["text"] == line
        assert "truncated" not in result["details"][0]["text"]

    def test_context_lines_also_truncated(self, project_dir: Path) -> None:
        """Context lines (not just match line) are truncated too."""
        long_ctx = "a" * 800
        (project_dir / "ctx.txt").write_text(f"{long_ctx}\nMATCH\nshort\n")

        result = search_files(project_dir, pattern=r"MATCH", context_lines=1)

        text = result["details"][0]["text"]
        lines = text.split("\n")
        # First line (context) should be truncated
        assert "... [line truncated: showing 500 of 800 chars]" in lines[0]
        # Match line should be intact
        assert lines[1] == "MATCH"


class TestSearchFilesCompactFallback:
    """Tests for compact fallback when results are truncated."""

    def test_files_key_present_when_truncated(self, project_dir: Path) -> None:
        """When truncated, 'matched_files' key contains complete file/line map."""
        lines = [f"match_{i}" for i in range(50)]
        (project_dir / "big.txt").write_text("\n".join(lines) + "\n")

        result = search_files(
            project_dir,
            pattern=r"match_",
            max_results=100,
            max_result_lines=1,  # tiny budget forces truncation
        )

        assert result["truncated"] is True
        assert "matched_files" in result
        files_entry = result["matched_files"][0]
        assert files_entry["file"].endswith("big.txt")
        # All 50 matches should be in the files map
        assert len(files_entry["lines"]) == 50

    def test_files_key_absent_when_not_truncated(self, project_dir: Path) -> None:
        """When not truncated, 'matched_files' key is not in the response."""
        (project_dir / "small.txt").write_text("hello world\n")

        result = search_files(project_dir, pattern=r"hello")

        assert result["truncated"] is False
        assert "matched_files" not in result

    def test_compact_fallback_multiple_files(self, project_dir: Path) -> None:
        """Compact fallback tracks matches across multiple files."""
        d = project_dir / "multi"
        d.mkdir()
        # Use long lines so char budget is exceeded quickly
        long_prefix = "z" * 100
        (d / "a.py").write_text(f"{long_prefix} target 1\n{long_prefix} target 2\n")
        (d / "b.py").write_text(f"{long_prefix} target 3\n")

        result = search_files(
            project_dir,
            glob="multi/*.py",
            pattern=r"target",
            max_results=100,
            max_result_lines=1,  # tiny budget = 120 chars
        )

        assert result["truncated"] is True
        assert result["total_matches"] == 3
        file_names = {e["file"] for e in result["matched_files"]}
        assert any("a.py" in f for f in file_names)
        assert any("b.py" in f for f in file_names)

    def test_empty_details_when_first_match_exceeds_budget(
        self, project_dir: Path
    ) -> None:
        """When first match exceeds char budget, details is empty but matched_files is populated."""
        long_line = "x" * 200
        (project_dir / "huge.txt").write_text(long_line + "\n")

        result = search_files(
            project_dir,
            glob="huge.txt",
            pattern=r"x+",
            max_results=100,
            max_result_lines=1,  # budget = 120 chars, truncated line = 200 chars
        )

        assert result["truncated"] is True
        assert result["details"] == []
        assert len(result["matched_files"]) == 1
        assert result["total_matches"] == 1

    def test_long_line_char_budget(self, project_dir: Path) -> None:
        """A single long-line match can exhaust char budget on its own."""
        # 600 char line, with max_result_lines=5 -> budget=600
        # After per-line truncation to 500 + marker, context is ~540 chars
        # Second match should not fit
        long = "x" * 600
        (project_dir / "two.txt").write_text(f"{long}\n{long}\n")

        result = search_files(
            project_dir,
            glob="two.txt",
            pattern=r"x+",
            max_results=100,
            max_result_lines=5,  # budget = 600
        )

        # At least one match fits, but both may not
        assert len(result["details"]) >= 1
        assert result["total_matches"] == 2
        assert result["truncated"] is True
        assert "matched_files" in result
