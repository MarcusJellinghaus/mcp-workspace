"""Unit tests for issue type factories."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from mcp_workspace.github_operations.issues.types import (
    create_empty_issue_data,
    issue_to_data,
)


def _github_issue(author_association: object = "MEMBER") -> MagicMock:
    label = MagicMock()
    label.name = "bug"
    assignee = MagicMock()
    assignee.login = "alice"
    github_issue = MagicMock()
    github_issue.number = 7
    github_issue.title = "Title"
    github_issue.body = None
    github_issue.state = "open"
    github_issue.labels = [label]
    github_issue.assignees = [assignee]
    github_issue.user.login = "octocat"
    github_issue.created_at = datetime(2024, 1, 2, 3, 4, 5)
    github_issue.updated_at = None
    github_issue.html_url = "https://github.com/test/repo/issues/7"
    github_issue.locked = False
    github_issue.author_association = author_association
    return github_issue


class TestIssueToData:
    """Test suite for the issue_to_data converter."""

    def test_copies_fields(self) -> None:
        """Test that every field is copied from the PyGithub issue."""
        result = issue_to_data(_github_issue())

        assert result == {
            "number": 7,
            "title": "Title",
            "body": "",
            "state": "open",
            "labels": ["bug"],
            "assignees": ["alice"],
            "user": "octocat",
            "created_at": "2024-01-02T03:04:05",
            "updated_at": None,
            "url": "https://github.com/test/repo/issues/7",
            "locked": False,
            "author_association": "MEMBER",
        }

    @pytest.mark.parametrize(
        "value", [MagicMock(), None, 5], ids=["mock", "none", "int"]
    )
    def test_non_string_association_is_none(self, value: object) -> None:
        """Test that a non-string author_association maps to None."""
        result = issue_to_data(_github_issue(author_association=value))

        assert result["author_association"] is None

    def test_ghost_user_is_none(self) -> None:
        """Test that a missing user maps to None."""
        github_issue = _github_issue()
        github_issue.user = None

        result = issue_to_data(github_issue)

        assert result["user"] is None


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
        assert result["author_association"] is None

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
