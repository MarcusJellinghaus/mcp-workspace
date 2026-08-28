"""Tests for output filtering with synthetic string inputs."""

from mcp_workspace.git_operations.output_filtering import (
    filter_content_output,
    filter_diff_output,
    filter_log_output,
    truncate_output,
)

# ---------------------------------------------------------------------------
# Synthetic test data
# ---------------------------------------------------------------------------

SAMPLE_DIFF = """\
diff --git a/foo.py b/foo.py
--- a/foo.py
+++ b/foo.py
@@ -1,5 +1,5 @@
 context line
-old_value = 42
+new_value = 99
 another context
 more context
diff --git a/bar.py b/bar.py
--- a/bar.py
+++ b/bar.py
@@ -10,3 +10,3 @@
 unrelated context
-unrelated_old
+unrelated_new"""

SAMPLE_CONTENT = """\
first line
second line
Fetch the issue
fourth line
fifth line"""

SAMPLE_LOG = """\
commit abc1234567890
Author: Test User <test@example.com>
Date:   Mon Jan 1 00:00:00 2024

    Fix critical bug in parser

commit def4567890123
Author: Test User <test@example.com>
Date:   Tue Jan 2 00:00:00 2024

    Add new feature for export"""


class TestFilterDiffOutput:
    """Structure-aware diff filtering tests."""

    def test_matching_hunk_includes_file_and_hunk_headers(self) -> None:
        result = filter_diff_output(SAMPLE_DIFF, "new_value")
        assert "diff --git a/foo.py b/foo.py" in result
        assert "@@" in result
        assert "new_value" in result

    def test_non_matching_hunk_excluded(self) -> None:
        result = filter_diff_output(SAMPLE_DIFF, "new_value")
        assert "unrelated" not in result

    def test_context_lines_around_match(self) -> None:
        result = filter_diff_output(SAMPLE_DIFF, "new_value", context=1)
        # Context=1 should include lines adjacent to the match
        assert "new_value" in result
        # The old_value line is adjacent to new_value in the hunk
        assert "old_value" in result

    def test_context_zero_shows_only_matching_lines(self) -> None:
        result = filter_diff_output(SAMPLE_DIFF, "new_value", context=0)
        assert "new_value" in result
        # With context=0, non-matching lines from the hunk should be excluded
        assert "context line" not in result
        assert "another context" not in result

    def test_multiple_files_only_matching_files_included(self) -> None:
        result = filter_diff_output(SAMPLE_DIFF, "unrelated")
        assert "bar.py" in result
        assert "foo.py" not in result

    def test_no_matches_returns_descriptive_message(self) -> None:
        result = filter_diff_output(SAMPLE_DIFF, "nonexistent_xyz")
        assert "No matches" in result
        assert "nonexistent_xyz" in result

    def test_search_is_case_insensitive(self) -> None:
        result = filter_diff_output(SAMPLE_DIFF, "NEW_VALUE")
        assert "new_value" in result

    def test_regex_pattern_in_search(self) -> None:
        result = filter_diff_output(SAMPLE_DIFF, "old_value|unrelated_old")
        assert "old_value" in result
        assert "unrelated_old" in result

    def test_invalid_regex_returns_error_message(self) -> None:
        result = filter_diff_output(SAMPLE_DIFF, "[unclosed")
        assert result.startswith("Invalid search pattern:")


class TestFilterContentOutput:
    """Line-based content filtering tests."""

    def test_match_returns_matching_line(self) -> None:
        result = filter_content_output(SAMPLE_CONTENT, "Fetch the issue", context=0)
        assert "Fetch the issue" in result

    def test_context_one_includes_adjacent_lines(self) -> None:
        result = filter_content_output(SAMPLE_CONTENT, "Fetch the issue", context=1)
        assert "second line" in result
        assert "fourth line" in result
        assert "first line" not in result
        assert "fifth line" not in result

    def test_context_zero_excludes_adjacent_lines(self) -> None:
        result = filter_content_output(SAMPLE_CONTENT, "Fetch the issue", context=0)
        assert "second line" not in result
        assert "fourth line" not in result

    def test_no_matches_returns_descriptive_message(self) -> None:
        result = filter_content_output(SAMPLE_CONTENT, "nonexistent_xyz")
        assert "No matches" in result
        assert "nonexistent_xyz" in result

    def test_search_is_case_insensitive(self) -> None:
        result = filter_content_output(SAMPLE_CONTENT, "FETCH", context=0)
        assert "Fetch the issue" in result

    def test_disjoint_regions_get_gap_separator(self) -> None:
        result = filter_content_output(SAMPLE_CONTENT, "first|fifth", context=0)
        assert result == "first line\n--\nfifth line"

    def test_contiguous_region_has_no_separator(self) -> None:
        result = filter_content_output(SAMPLE_CONTENT, "Fetch the issue", context=1)
        assert "--" not in result

    def test_invalid_regex_returns_error_message(self) -> None:
        result = filter_content_output(SAMPLE_CONTENT, "[unclosed")
        assert result.startswith("Invalid search pattern:")


class TestFilterLogOutput:
    """Structure-aware log filtering tests."""

    def test_matching_commit_includes_entire_entry(self) -> None:
        result = filter_log_output(SAMPLE_LOG, "parser")
        assert "commit abc1234567890" in result
        assert "Fix critical bug in parser" in result

    def test_non_matching_commit_excluded(self) -> None:
        result = filter_log_output(SAMPLE_LOG, "parser")
        assert "export" not in result
        assert "def4567890123" not in result

    def test_multi_line_commit_message_matched(self) -> None:
        result = filter_log_output(SAMPLE_LOG, "export")
        assert "commit def4567890123" in result
        assert "Add new feature for export" in result

    def test_no_matches_returns_descriptive_message(self) -> None:
        result = filter_log_output(SAMPLE_LOG, "nonexistent_xyz")
        assert "No matches" in result
        assert "nonexistent_xyz" in result

    def test_search_is_case_insensitive(self) -> None:
        result = filter_log_output(SAMPLE_LOG, "PARSER")
        assert "Fix critical bug in parser" in result

    def test_invalid_regex_returns_error_message(self) -> None:
        result = filter_log_output(SAMPLE_LOG, "[unclosed")
        assert result.startswith("Invalid search pattern:")


class TestTruncateOutput:
    """Truncation tests."""

    def test_within_limit_unchanged(self) -> None:
        text = "line1\nline2\nline3"
        assert truncate_output(text, max_lines=5) == text

    def test_over_limit_truncated_with_notice(self) -> None:
        text = "line1\nline2\nline3\nline4\nline5"
        result = truncate_output(text, max_lines=3)
        assert "line1" in result
        assert "line3" in result
        assert "line4" not in result
        assert "[truncated" in result
        assert "showing 3 of 5 lines" in result
        assert "max_lines=5" in result

    def test_exact_limit_unchanged(self) -> None:
        text = "line1\nline2\nline3"
        assert truncate_output(text, max_lines=3) == text

    def test_notice_shows_cap_and_total(self) -> None:
        text = "line1\nline2\nline3\nline4\nline5"
        result = truncate_output(text, max_lines=2)
        assert "showing 2 of 5 lines" in result
        assert "max_lines=5" in result

    def test_empty_string(self) -> None:
        assert truncate_output("", max_lines=10) == ""
