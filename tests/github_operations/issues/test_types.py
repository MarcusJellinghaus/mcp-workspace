"""Unit tests for issue type factories."""

from mcp_workspace.github_operations.issues.types import create_empty_issue_data


class TestCreateEmptyIssueData:
    """Test suite for the create_empty_issue_data factory function."""

    def test_returns_all_default_fields(self) -> None:
        """Test that every field is set to its documented default value."""
        result = create_empty_issue_data()

        assert result["number"] == 0
        assert result["title"] == ""
        assert result["body"] == ""
        assert result["state"] == ""
        assert result["labels"] == []
        assert result["assignees"] == []
        assert result["user"] is None
        assert result["created_at"] is None
        assert result["updated_at"] is None
        assert result["url"] == ""
        assert result["locked"] is False

    def test_base_branch_key_absent(self) -> None:
        """Test that the NotRequired base_branch key is not set."""
        result = create_empty_issue_data()

        assert "base_branch" not in result

    def test_returns_independent_instances(self) -> None:
        """Test that each call returns fresh, independent list objects."""
        first = create_empty_issue_data()
        second = create_empty_issue_data()

        first["labels"].append("bug")
        first["assignees"].append("octocat")

        assert second["labels"] == []
        assert second["assignees"] == []
