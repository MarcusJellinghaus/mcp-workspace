"""Unit tests for IssueManager comment operations with mocked dependencies."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.issues import IssueManager
from mcp_workspace.github_operations.issues.base import (
    validate_comment_id,
    validate_issue_number,
)


@pytest.mark.git_integration
class TestIssueManagerComments:
    """Unit tests for IssueManager comment operations with mocked dependencies."""

    def test_add_comment_success(self, mock_issue_manager: IssueManager) -> None:
        """Test successful comment addition."""
        issue_number = 1
        comment_body = "Test comment"
        mock_issue = MagicMock()
        mock_comment = MagicMock()
        mock_comment.id = 123
        mock_comment.body = comment_body

        mock_issue_manager._repository.get_issue.return_value = mock_issue
        mock_issue.create_comment.return_value = mock_comment

        result = mock_issue_manager.add_comment(issue_number, comment_body)

        assert result["id"] == 123
        assert result["body"] == comment_body
        mock_issue.create_comment.assert_called_once_with(comment_body)

    def test_add_comment_empty_body(self, mock_issue_manager: IssueManager) -> None:
        """Test that empty comment body raises ValueError."""
        with pytest.raises(ValueError, match="Comment body cannot be empty"):
            mock_issue_manager.add_comment(1, "")

    def test_add_comment_invalid_issue_number(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test adding comment with invalid issue number."""
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            mock_issue_manager.add_comment(0, "Test comment")

    def test_add_comment_auth_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that authentication errors are raised when adding comments."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.add_comment(1, "Test comment")

    def test_get_comments_success(self, mock_issue_manager: IssueManager) -> None:
        """Test successful comment retrieval."""
        issue_number = 1
        mock_issue = MagicMock()
        mock_comment1 = MagicMock()
        mock_comment1.id = 123
        mock_comment1.body = "Comment 1"
        mock_comment2 = MagicMock()
        mock_comment2.id = 124
        mock_comment2.body = "Comment 2"

        mock_issue_manager._repository.get_issue.return_value = mock_issue
        mock_issue.get_comments.return_value = [mock_comment1, mock_comment2]

        result = mock_issue_manager.get_comments(issue_number)

        assert len(result) == 2
        assert result[0]["id"] == 123
        assert result[1]["id"] == 124

    def test_get_comments_empty_list(self, mock_issue_manager: IssueManager) -> None:
        """Test getting comments from issue with no comments."""
        issue_number = 1
        mock_issue = MagicMock()

        mock_issue_manager._repository.get_issue.return_value = mock_issue
        mock_issue.get_comments.return_value = []

        result = mock_issue_manager.get_comments(issue_number)

        assert len(result) == 0

    def test_get_comments_invalid_issue_number(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test getting comments with invalid issue number."""
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            mock_issue_manager.get_comments(0)

    def test_get_comments_auth_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that authentication errors are raised when getting comments."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.get_comments(1)

    def test_edit_comment_success(self, mock_issue_manager: IssueManager) -> None:
        """Test successful comment editing."""
        issue_number = 1
        comment_id = 123
        new_body = "Updated comment"
        mock_issue = MagicMock()
        mock_comment = MagicMock()
        mock_comment.id = comment_id
        mock_comment.body = new_body

        mock_issue_manager._repository.get_issue.return_value = mock_issue
        mock_issue.get_comment.return_value = mock_comment

        mock_issue_manager.edit_comment(issue_number, comment_id, new_body)

        mock_comment.edit.assert_called_once_with(new_body)

    def test_edit_comment_empty_body(self, mock_issue_manager: IssueManager) -> None:
        """Test that empty comment body raises ValueError."""
        with pytest.raises(ValueError, match="Comment body cannot be empty"):
            mock_issue_manager.edit_comment(1, 123, "")

    def test_edit_comment_invalid_issue_number(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test editing comment with invalid issue number."""
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            mock_issue_manager.edit_comment(0, 123, "Updated")

    def test_edit_comment_invalid_comment_id(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test editing comment with invalid comment ID."""
        with pytest.raises(ValueError, match="Comment ID must be a positive integer"):
            mock_issue_manager.edit_comment(1, 0, "Updated")

    def test_edit_comment_auth_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that authentication errors are raised when editing comments."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.edit_comment(1, 123, "Updated")

    def test_delete_comment_success(self, mock_issue_manager: IssueManager) -> None:
        """Test successful comment deletion."""
        issue_number = 1
        comment_id = 123
        mock_issue = MagicMock()
        mock_comment = MagicMock()
        mock_comment.id = comment_id

        mock_issue_manager._repository.get_issue.return_value = mock_issue
        mock_issue.get_comment.return_value = mock_comment

        mock_issue_manager.delete_comment(issue_number, comment_id)

        mock_comment.delete.assert_called_once()

    def test_delete_comment_invalid_issue_number(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test deleting comment with invalid issue number."""
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            mock_issue_manager.delete_comment(0, 123)

    def test_delete_comment_invalid_comment_id(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test deleting comment with invalid comment ID."""
        with pytest.raises(ValueError, match="Comment ID must be a positive integer"):
            mock_issue_manager.delete_comment(1, 0)

    def test_delete_comment_auth_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that authentication errors are raised when deleting comments."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.delete_comment(1, 123)
