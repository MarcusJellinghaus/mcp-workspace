"""Unit tests for compact_diffs.py — all synthetic string inputs, no git repos."""

from mcp_workspace.git_operations.compact_diffs import (
    MIN_BLOCK_LINES,
    MIN_CONTENT_LENGTH,
    PREVIEW_LINES,
    FileDiff,
    Hunk,
    collect_line_occurrences,
    collect_line_sources,
    extract_moved_blocks_ansi,
    find_moved_lines,
    format_moved_summary,
    is_moved_line,
    is_significant_line,
    parse_diff,
    render_compact_diff,
    render_file_diff,
    render_hunk,
    strip_ansi,
)

# ---------------------------------------------------------------------------
# TestParseHunkHeader
# ---------------------------------------------------------------------------


class TestParseHunkHeader:
    """Tests that hunk headers are parsed correctly."""

    def test_parse_single_hunk_header(self) -> None:
        diff = (
            "diff --git a.py b.py\n"
            "--- a.py\n"
            "+++ b.py\n"
            "@@ -1,5 +1,3 @@\n"
            " context\n"
            "-removed\n"
            "+added\n"
        )
        files = parse_diff(diff)
        assert len(files) == 1
        assert len(files[0].hunks) == 1
        assert files[0].hunks[0].header == "@@ -1,5 +1,3 @@"

    def test_parse_multiple_hunks_in_file(self) -> None:
        diff = (
            "diff --git a.py b.py\n"
            "--- a.py\n"
            "+++ b.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-old line one\n"
            "+new line one\n"
            "@@ -10,2 +10,2 @@\n"
            "-old line two\n"
            "+new line two\n"
        )
        files = parse_diff(diff)
        assert len(files) == 1
        assert len(files[0].hunks) == 2
        assert files[0].hunks[0].header == "@@ -1,2 +1,2 @@"
        assert files[0].hunks[1].header == "@@ -10,2 +10,2 @@"


# ---------------------------------------------------------------------------
# TestParseDiff
# ---------------------------------------------------------------------------


class TestParseDiff:
    """Tests that a multi-file diff is parsed into correct FileDiff objects."""

    def test_parse_two_file_diff(self) -> None:
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,3 +1,3 @@\n"
            " context line\n"
            "-removed line\n"
            "+added line\n"
            "diff --git a/bar.py b/bar.py\n"
            "--- a/bar.py\n"
            "+++ b/bar.py\n"
            "@@ -5,2 +5,2 @@\n"
            "-old content\n"
            "+new content\n"
        )
        files = parse_diff(diff)
        assert len(files) == 2
        assert files[0].headers[0] == "diff --git a/foo.py b/foo.py"
        assert files[1].headers[0] == "diff --git a/bar.py b/bar.py"
        assert len(files[0].hunks) == 1
        assert len(files[1].hunks) == 1

    def test_parse_empty_diff(self) -> None:
        assert parse_diff("") == []
        assert parse_diff("   \n  ") == []

    def test_file_headers_captured(self) -> None:
        diff = (
            "diff --git a/x.py b/x.py\n"
            "index abc..def 100644\n"
            "--- a/x.py\n"
            "+++ b/x.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-old\n"
            "+new\n"
        )
        files = parse_diff(diff)
        assert len(files[0].headers) == 4  # diff, index, ---, +++


# ---------------------------------------------------------------------------
# TestStripAnsi
# ---------------------------------------------------------------------------


class TestStripAnsi:
    """Tests for stripping ANSI escape sequences."""

    def test_no_ansi_unchanged(self) -> None:
        assert strip_ansi("hello world") == "hello world"

    def test_strips_colour_codes(self) -> None:
        coloured = "\x1b[31mred text\x1b[0m"
        assert strip_ansi(coloured) == "red text"

    def test_strips_dim_code(self) -> None:
        dim = "\x1b[2m+moved line content\x1b[0m"
        assert strip_ansi(dim) == "+moved line content"


# ---------------------------------------------------------------------------
# TestIsMovedLine
# ---------------------------------------------------------------------------


class TestIsMovedLine:
    """Tests for ANSI-based moved-line detection."""

    def test_context_line_is_not_moved(self) -> None:
        assert is_moved_line(" context line") is False

    def test_plain_added_line_is_not_moved(self) -> None:
        assert is_moved_line("+plain added line") is False

    def test_dim_added_line_is_moved(self) -> None:
        # git --color-moved=dimmed-zebra emits SGR code 2 (dim) for moved lines
        dim_line = "\x1b[2m+moved line content here\x1b[0m"
        assert is_moved_line(dim_line) is True

    def test_dim_removed_line_is_moved(self) -> None:
        dim_line = "\x1b[2m-moved line content here\x1b[0m"
        assert is_moved_line(dim_line) is True

    def test_header_line_is_not_moved(self) -> None:
        assert is_moved_line("@@ -1,5 +1,5 @@") is False


# ---------------------------------------------------------------------------
# TestExtractMovedBlocksAnsi
# ---------------------------------------------------------------------------


class TestExtractMovedBlocksAnsi:
    """Tests for extracting moved-line contents from an ANSI diff."""

    def test_extract_moved_lines(self) -> None:
        ansi_diff = (
            " context line\n"
            "\x1b[2m+moved line content here\x1b[0m\n"
            "+plain added line\n"
            "\x1b[2m-another moved line content\x1b[0m\n"
        )
        moved = extract_moved_blocks_ansi(ansi_diff)
        assert "moved line content here" in moved
        assert "another moved line content" in moved
        assert "plain added line" not in moved

    def test_empty_diff_returns_empty_set(self) -> None:
        assert extract_moved_blocks_ansi("") == set()


# ---------------------------------------------------------------------------
# TestIsSignificantLine
# ---------------------------------------------------------------------------


class TestIsSignificantLine:
    """Tests for the significance threshold."""

    def test_short_line_not_significant(self) -> None:
        assert is_significant_line("pass") is False
        assert is_significant_line("}") is False
        assert is_significant_line("") is False

    def test_long_line_is_significant(self) -> None:
        assert is_significant_line("def my_function(arg1, arg2):") is True
        assert is_significant_line("x" * MIN_CONTENT_LENGTH) is True

    def test_boundary_condition(self) -> None:
        # Exactly MIN_CONTENT_LENGTH chars → significant
        assert is_significant_line("a" * MIN_CONTENT_LENGTH) is True
        # One less → not significant
        assert is_significant_line("a" * (MIN_CONTENT_LENGTH - 1)) is False


# ---------------------------------------------------------------------------
# TestCollectLineOccurrences
# ---------------------------------------------------------------------------


class TestCollectLineOccurrences:
    """Tests for collecting removed/added line sets from FileDiff objects."""

    def test_collects_removed_and_added(self) -> None:
        hunk = Hunk(
            header="@@ -1,3 +1,3 @@",
            lines=[
                " context line here in file",
                "-removed significant line content",
                "+added significant line content",
                "-}",  # short — should be ignored
            ],
        )
        file_diff = FileDiff(headers=["diff --git a.py b.py"], hunks=[hunk])
        removed, added = collect_line_occurrences([file_diff])
        assert "removed significant line content" in removed
        assert "added significant line content" in added
        assert "}" not in removed  # too short

    def test_empty_files_returns_empty_sets(self) -> None:
        removed, added = collect_line_occurrences([])
        assert removed == set()
        assert added == set()


# ---------------------------------------------------------------------------
# TestFindMovedLines
# ---------------------------------------------------------------------------


class TestFindMovedLines:
    """Tests for Python-based cross-file move detection."""

    def test_intersection_of_removed_and_added(self) -> None:
        hunk1 = Hunk(
            header="@@ -1,2 +1,2 @@",
            lines=[
                "-def some_function_name(param):",
                "-    return param * 2",
            ],
        )
        hunk2 = Hunk(
            header="@@ -1,2 +1,2 @@",
            lines=[
                "+def some_function_name(param):",
                "+    return param * 2",
            ],
        )
        file1 = FileDiff(headers=["diff --git a.py b.py"], hunks=[hunk1])
        file2 = FileDiff(headers=["diff --git b.py c.py"], hunks=[hunk2])
        moved = find_moved_lines([file1, file2])
        assert "def some_function_name(param):" in moved
        assert "return param * 2" in moved

    def test_unique_lines_not_in_intersection(self) -> None:
        hunk = Hunk(
            header="@@ -1,1 +1,1 @@",
            lines=["-only removed long line here", "+only added long line here"],
        )
        file_diff = FileDiff(headers=["diff --git a.py b.py"], hunks=[hunk])
        moved = find_moved_lines([file_diff])
        assert len(moved) == 0


# ---------------------------------------------------------------------------
# TestFormatMovedSummary
# ---------------------------------------------------------------------------


class TestFormatMovedSummary:
    """Tests for the moved-block summary comment format."""

    def test_format_five_lines(self) -> None:
        assert format_moved_summary(5) == "# [moved: 5 lines not shown]"

    def test_format_one_line(self) -> None:
        assert format_moved_summary(1) == "# [moved: 1 lines not shown]"

    def test_format_large_count(self) -> None:
        result = format_moved_summary(100)
        assert "100" in result
        assert result.startswith("# [moved:")

    def test_format_with_source_file_addition(self) -> None:
        result = format_moved_summary(10, "src/foo.py", is_addition=True)
        assert result == "# [moved from src/foo.py: 10 lines not shown]"

    def test_format_with_dest_file_deletion(self) -> None:
        result = format_moved_summary(10, "src/bar.py", is_addition=False)
        assert result == "# [moved to src/bar.py: 10 lines not shown]"


# ---------------------------------------------------------------------------
# TestRenderHunk
# ---------------------------------------------------------------------------


class TestRenderHunk:
    """Tests for hunk rendering with moved-block suppression."""

    def test_small_block_kept(self) -> None:
        # Block of 2 lines (< MIN_BLOCK_LINES) → kept as-is
        hunk = Hunk(
            header="@@ -1,2 +1,2 @@",
            lines=[
                "-def some_function(param_a):",
                "-    return param_a * 2",
            ],
        )
        moved = {"def some_function(param_a):": True, "    return param_a * 2": True}
        result = render_hunk(hunk, set(moved.keys()))
        assert "-def some_function(param_a):" in result
        assert "moved" not in result

    def test_large_moved_block_suppressed(self) -> None:
        # Block of MIN_BLOCK_LINES where all significant lines are moved:
        # first PREVIEW_LINES are shown as preview, rest summarised.
        lines = [f"+def function_line_{i}(some_param):" for i in range(MIN_BLOCK_LINES)]
        moved = {f"def function_line_{i}(some_param):" for i in range(MIN_BLOCK_LINES)}
        hunk = Hunk(header="@@ -1,5 +1,5 @@", lines=lines)
        result = render_hunk(hunk, moved)
        assert "+def function_line_0(some_param):" in result  # preview shown
        assert "# [moved" in result  # summary present
        assert f"{MIN_BLOCK_LINES - PREVIEW_LINES} lines not shown" in result

    def test_context_lines_always_kept(self) -> None:
        hunk = Hunk(
            header="@@ -1,3 +1,3 @@",
            lines=[
                " this is a context line here",
                "-def some_function(param_a):",
                "+def some_function(param_a):",
            ],
        )
        moved: set[str] = set()
        result = render_hunk(hunk, moved)
        assert "this is a context line here" in result

    def test_suppressed_hunk_emits_summary(self) -> None:
        # All lines in a block >= MIN_BLOCK_LINES that are all moved → replaced by summary
        lines = [f"+def function_line_{i}(some_param):" for i in range(MIN_BLOCK_LINES)]
        moved = {f"def function_line_{i}(some_param):" for i in range(MIN_BLOCK_LINES)}
        hunk = Hunk(header="@@ -1,3 +1,3 @@", lines=lines)
        result = render_hunk(hunk, moved)
        assert "# [moved:" in result

    def test_moved_block_after_non_moved_header_suppressed(self) -> None:
        # New-file hunk: non-moved header line followed by a large moved block.
        # The non-moved header must be kept; the moved block must show preview + summary.
        non_moved_header = "+# unique non-moved header line here"
        moved_lines_content = [
            f"+def function_line_{i}(some_param):" for i in range(MIN_BLOCK_LINES)
        ]
        moved = {f"def function_line_{i}(some_param):" for i in range(MIN_BLOCK_LINES)}
        hunk = Hunk(
            header="@@ -0,0 +1,6 @@",
            lines=[non_moved_header] + moved_lines_content,
        )
        result = render_hunk(hunk, moved)
        assert "unique non-moved header line here" in result
        assert "+def function_line_0(some_param):" in result  # preview shown
        assert "lines not shown" in result

    def test_preview_lines_shown_before_summary(self) -> None:
        # Exactly PREVIEW_LINES preview lines visible; lines beyond are hidden.
        lines = [
            f"+def function_line_{i}(some_param_long_name):"
            for i in range(MIN_BLOCK_LINES)
        ]
        moved = {
            f"def function_line_{i}(some_param_long_name):"
            for i in range(MIN_BLOCK_LINES)
        }
        hunk = Hunk(header="@@ -1,5 +1,5 @@", lines=lines)
        result = render_hunk(hunk, moved)
        for i in range(PREVIEW_LINES):
            assert f"+def function_line_{i}(some_param_long_name):" in result
        for i in range(PREVIEW_LINES, MIN_BLOCK_LINES):
            assert f"+def function_line_{i}(some_param_long_name):" not in result
        assert "lines not shown" in result


# ---------------------------------------------------------------------------
# TestCollectLineSources
# ---------------------------------------------------------------------------


class TestCollectLineSources:
    """Tests for file-source tracking."""

    def test_removed_line_maps_to_its_file(self) -> None:
        hunk = Hunk(
            header="@@ -1,1 +1,1 @@",
            lines=["-def some_function_name(param):"],
        )
        file_diff = FileDiff(
            headers=["diff --git a/src/foo.py b/src/foo.py"], hunks=[hunk]
        )
        removed_to_file, added_to_file = collect_line_sources([file_diff])
        assert removed_to_file.get("def some_function_name(param):") == "b/src/foo.py"
        assert "def some_function_name(param):" not in added_to_file

    def test_added_line_maps_to_its_file(self) -> None:
        hunk = Hunk(
            header="@@ -1,1 +1,1 @@",
            lines=["+def some_function_name(param):"],
        )
        file_diff = FileDiff(
            headers=["diff --git a/src/bar.py b/src/bar.py"], hunks=[hunk]
        )
        removed_to_file, added_to_file = collect_line_sources([file_diff])
        assert added_to_file.get("def some_function_name(param):") == "b/src/bar.py"
        assert "def some_function_name(param):" not in removed_to_file

    def test_empty_files_returns_empty_dicts(self) -> None:
        removed_to_file, added_to_file = collect_line_sources([])
        assert removed_to_file == {}
        assert added_to_file == {}


# ---------------------------------------------------------------------------
# TestRenderFileDiff
# ---------------------------------------------------------------------------


class TestRenderFileDiff:
    """Tests for file-level rendering."""

    def test_file_with_only_moved_hunks_emits_summary(self) -> None:
        # A hunk where all lines are a moved block → preview + summary shown,
        # so file is included in output (not skipped)
        lines = [f"+def function_line_{i}(some_param):" for i in range(MIN_BLOCK_LINES)]
        moved = {f"def function_line_{i}(some_param):" for i in range(MIN_BLOCK_LINES)}
        hunk = Hunk(header="@@ -1,5 +1,5 @@", lines=lines)
        file_diff = FileDiff(headers=["diff --git a.py b.py"], hunks=[hunk])
        result = render_file_diff(file_diff, moved)
        assert "# [moved" in result

    def test_file_with_real_changes_rendered(self) -> None:
        hunk = Hunk(
            header="@@ -1,2 +1,2 @@",
            lines=[
                "-old unique content here in file",
                "+new unique content here in file",
            ],
        )
        file_diff = FileDiff(
            headers=["diff --git a.py b.py", "--- a.py", "+++ b.py"],
            hunks=[hunk],
        )
        result = render_file_diff(file_diff, set())
        assert "diff --git a.py b.py" in result
        assert "old unique content here in file" in result

    def test_file_headers_emitted_when_no_parsed_hunks(self) -> None:
        file_diff = FileDiff(
            headers=["diff --git a.py b.py", "similarity index 100%"],
            hunks=[],
        )
        result = render_file_diff(file_diff, set())
        for header in file_diff.headers:
            assert header in result

    def test_pure_rename_headers_emitted(self) -> None:
        file_diff = FileDiff(
            headers=[
                "diff --git a/old.py b/new.py",
                "similarity index 100%",
                "rename from old.py",
                "rename to new.py",
            ],
            hunks=[],
        )
        result = render_file_diff(file_diff, set())
        for header in file_diff.headers:
            assert header in result

    def test_partial_rename_emits_headers_and_hunks(self) -> None:
        file_diff = FileDiff(
            headers=[
                "diff --git a/old.py b/new.py",
                "similarity index 80%",
                "rename from old.py",
                "rename to new.py",
                "--- a/old.py",
                "+++ b/new.py",
            ],
            hunks=[
                Hunk(
                    header="@@ -1,2 +1,2 @@",
                    lines=[
                        "-old unique content here in file",
                        "+new unique content here in file",
                    ],
                )
            ],
        )
        result = render_file_diff(file_diff, set())
        assert "rename from old.py" in result
        assert "rename to new.py" in result
        assert "old unique content here in file" in result
        assert "new unique content here in file" in result

    def test_pure_copy_headers_emitted(self) -> None:
        file_diff = FileDiff(
            headers=[
                "diff --git a/src.py b/dst.py",
                "similarity index 100%",
                "copy from src.py",
                "copy to dst.py",
            ],
            hunks=[],
        )
        result = render_file_diff(file_diff, set())
        for header in file_diff.headers:
            assert header in result

    def test_partial_copy_emits_headers_and_hunks(self) -> None:
        file_diff = FileDiff(
            headers=[
                "diff --git a/src.py b/dst.py",
                "similarity index 85%",
                "copy from src.py",
                "copy to dst.py",
                "--- a/src.py",
                "+++ b/dst.py",
            ],
            hunks=[
                Hunk(
                    header="@@ -1,2 +1,2 @@",
                    lines=[
                        "-old unique content here in file",
                        "+new unique content here in file",
                    ],
                )
            ],
        )
        result = render_file_diff(file_diff, set())
        assert "copy from src.py" in result
        assert "copy to dst.py" in result
        assert "old unique content here in file" in result

    def test_mode_change_headers_emitted(self) -> None:
        file_diff = FileDiff(
            headers=[
                "diff --git a/script.sh b/script.sh",
                "old mode 100644",
                "new mode 100755",
            ],
            hunks=[],
        )
        result = render_file_diff(file_diff, set())
        for header in file_diff.headers:
            assert header in result

    def test_binary_change_headers_emitted(self) -> None:
        file_diff = FileDiff(
            headers=[
                "diff --git a/image.png b/image.png",
                "Binary files a/image.png and b/image.png differ",
            ],
            hunks=[],
        )
        result = render_file_diff(file_diff, set())
        for header in file_diff.headers:
            assert header in result

    def test_empty_file_creation_headers_emitted(self) -> None:
        file_diff = FileDiff(
            headers=[
                "diff --git a/empty.py b/empty.py",
                "new file mode 100644",
            ],
            hunks=[],
        )
        result = render_file_diff(file_diff, set())
        for header in file_diff.headers:
            assert header in result

    def test_empty_file_deletion_headers_emitted(self) -> None:
        file_diff = FileDiff(
            headers=[
                "diff --git a/empty.py b/empty.py",
                "deleted file mode 100644",
            ],
            hunks=[],
        )
        result = render_file_diff(file_diff, set())
        for header in file_diff.headers:
            assert header in result

    def test_moved_suppression_still_hides_collapsed_hunks(self) -> None:
        """Hunks that all collapse to '' via moved-block suppression → return ''."""
        # Create a hunk with only context + the hunk header, which renders to ""
        # when all +/- lines are suppressed. We simulate this by having a hunk
        # that after render_hunk returns "" (only header remained).
        hunk = Hunk(
            header="@@ -1,1 +1,1 @@",
            lines=[],  # empty lines → render_hunk returns ""
        )
        file_diff = FileDiff(
            headers=["diff --git a/foo.py b/foo.py"],
            hunks=[hunk],
        )
        result = render_file_diff(file_diff, set())
        assert result == ""


# ---------------------------------------------------------------------------
# TestRenderCompactDiff
# ---------------------------------------------------------------------------


class TestRenderCompactDiff:
    """End-to-end tests for the compact diff renderer."""

    def test_render_compact_diff_empty_input(self) -> None:
        assert render_compact_diff("", "") == ""

    def test_render_compact_diff_whitespace_only(self) -> None:
        assert render_compact_diff("   \n  ", "") == ""

    def test_moved_lines_suppressed_in_output(self) -> None:
        # Synthetic 10-line diff where one block of 3+ lines appears in both removed/added
        moved_content = [
            "def calculate_total_price(items, tax_rate):",
            "    subtotal = sum(item.price for item in items)",
            "    tax = subtotal * tax_rate",
            "    total = subtotal + tax",
            "    return total",
        ]
        removed_block = "\n".join(f"-{line}" for line in moved_content)
        added_block = "\n".join(f"+{line}" for line in moved_content)

        plain_diff = (
            "diff --git a/module_a.py b/module_a.py\n"
            "--- a/module_a.py\n"
            "+++ b/module_a.py\n"
            "@@ -1,5 +1,5 @@\n"
            " context line one here\n"
            f"{removed_block}\n"
            " context line two here\n"
            "diff --git a/module_b.py b/module_b.py\n"
            "--- a/module_b.py\n"
            "+++ b/module_b.py\n"
            "@@ -1,5 +1,5 @@\n"
            " context line three here\n"
            f"{added_block}\n"
            " context line four here\n"
        )
        result = render_compact_diff(plain_diff, "")
        # The moved block should be suppressed with preview + summary
        assert "# [moved" in result
        assert "lines not shown" in result

    def test_unique_changes_preserved(self) -> None:
        plain_diff = (
            "diff --git a/new_feature.py b/new_feature.py\n"
            "--- a/new_feature.py\n"
            "+++ b/new_feature.py\n"
            "@@ -1,3 +1,3 @@\n"
            " context line present here\n"
            "-completely unique removed line in diff\n"
            "+completely unique added line in diff\n"
        )
        result = render_compact_diff(plain_diff, "")
        assert "completely unique removed line in diff" in result
        assert "completely unique added line in diff" in result
        assert "# [moved:" not in result
