"""Unit tests for branch naming utilities."""

from mcp_workspace.github_operations.issues import (
    generate_branch_name_from_issue,
)


class TestBranchNameGeneration:
    """Test suite for branch name generation utility function."""

    def test_basic_sanitization(self) -> None:
        """Test basic branch name generation with simple title."""
        result = generate_branch_name_from_issue(123, "Add New Feature")
        assert result == "123-add-new-feature"

    def test_dash_conversion(self) -> None:
        """Test that ' - ' is converted to '---' (GitHub-specific rule)."""
        result = generate_branch_name_from_issue(456, "Add New Feature - Part 1")
        assert result == "456-add-new-feature---part-1"

    def test_lowercase(self) -> None:
        """Test that all characters are converted to lowercase."""
        result = generate_branch_name_from_issue(789, "FIX BUG IN MODULE")
        assert result == "789-fix-bug-in-module"

    def test_alphanumeric_only(self) -> None:
        """Test that non-alphanumeric characters (except dash) are converted to dashes."""
        result = generate_branch_name_from_issue(101, "Fix bug #42 & issue @123")
        assert result == "101-fix-bug-42-issue-123"

    def test_spaces_to_dashes(self) -> None:
        """Test that spaces are converted to dashes."""
        result = generate_branch_name_from_issue(202, "Update user interface")
        assert result == "202-update-user-interface"

    def test_strip_leading_trailing_dashes(self) -> None:
        """Test that leading and trailing dashes are stripped."""
        result = generate_branch_name_from_issue(303, "!!!Important Fix!!!")
        assert result == "303-important-fix"

    def test_truncation_preserves_issue_number(self) -> None:
        """Test that truncation keeps issue number and truncates title."""
        long_title = "A" * 300  # Very long title
        result = generate_branch_name_from_issue(404, long_title, max_length=50)

        # Should start with "404-"
        assert result.startswith("404-")
        # Should be exactly max_length characters
        assert len(result) == 50
        # Should not end with a dash
        assert not result.endswith("-")

    def test_empty_title(self) -> None:
        """Test handling of empty or whitespace-only title."""
        result = generate_branch_name_from_issue(505, "")
        assert result == "505"

        result = generate_branch_name_from_issue(606, "   ")
        assert result == "606"

    def test_special_characters(self) -> None:
        """Test handling of various special characters."""
        result = generate_branch_name_from_issue(707, "Fix: Bug! (Urgent) @user #tag")
        assert result == "707-fix-bug-urgent-user-tag"

    def test_multiple_spaces(self) -> None:
        """Test that multiple consecutive spaces are collapsed to single dash."""
        result = generate_branch_name_from_issue(808, "Fix    multiple     spaces")
        assert result == "808-fix-multiple-spaces"

    def test_unicode_characters(self) -> None:
        """Test handling of Unicode characters."""
        result = generate_branch_name_from_issue(909, "Add café and naïve handling")
        # Unicode characters should be replaced with dashes
        assert result.startswith("909-")
        # Should only contain lowercase alphanumeric and dashes
        assert all(c.isalnum() or c == "-" for c in result)

    def test_emoji_handling(self) -> None:
        """Test handling of emoji characters."""
        result = generate_branch_name_from_issue(1010, "🚀 Launch new feature 🎉")
        # Emojis should be replaced with dashes
        assert result.startswith("1010-")
        # Should only contain lowercase alphanumeric and dashes
        assert all(c.isalnum() or c == "-" for c in result)

    def test_multiple_consecutive_dashes_collapsed(self) -> None:
        """Test that multiple consecutive dashes are collapsed to single dash."""
        result = generate_branch_name_from_issue(1111, "Fix---multiple---dashes")
        assert "---" not in result or result.count("---") == 1  # Only from " - "

    def test_custom_max_length(self) -> None:
        """Test custom max_length parameter."""
        long_title = "B" * 200
        result = generate_branch_name_from_issue(1212, long_title, max_length=100)
        assert len(result) == 100
        assert result.startswith("1212-")

    def test_default_max_length(self) -> None:
        """Test default max_length of 200 characters."""
        long_title = "C" * 300
        result = generate_branch_name_from_issue(1313, long_title)
        assert len(result) == 200
        assert result.startswith("1313-")

    def test_title_with_only_special_characters(self) -> None:
        """Test title containing only special characters."""
        result = generate_branch_name_from_issue(1414, "!!!@@@###$$$")
        # Should strip all special chars and dashes, leaving only issue number
        assert result == "1414"

    def test_mixed_alphanumeric_and_special(self) -> None:
        """Test mixed alphanumeric and special characters."""
        result = generate_branch_name_from_issue(1515, "v1.2.3-beta+build.456")
        assert result == "1515-v1-2-3-beta-build-456"

    def test_preserves_numbers_in_title(self) -> None:
        """Test that numbers in the title are preserved."""
        result = generate_branch_name_from_issue(1616, "Update API v2 to v3")
        assert result == "1616-update-api-v2-to-v3"

    def test_github_dash_separator_rule(self) -> None:
        """Test GitHub's specific rule for ' - ' separator."""
        # Single occurrence
        result = generate_branch_name_from_issue(1717, "Feature A - Part 1")
        assert "---" in result

        # Multiple occurrences
        result = generate_branch_name_from_issue(1818, "A - B - C")
        assert result == "1818-a---b---c"
