"""Tests for PullRequestManager.reply_to_review_comment() method.

Tests replying to an inline PR review comment using mocked GitHub API.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.pr_manager import PullRequestManager

from ._pr_test_helpers import create_mock_pr


@pytest.mark.git_integration
class TestReplyToReviewComment:
    """Tests for reply_to_review_comment() method."""

    @patch("mcp_workspace.github_operations._client.Github")
    def test_reply_to_review_comment_success(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Test successful reply to a review comment."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_reply = MagicMock()
        mock_reply.id = 456
        mock_reply.body = "Thanks, fixed."
        mock_reply.user.login = "testuser"
        mock_reply.created_at.isoformat.return_value = "2023-01-01T00:00:00Z"
        mock_reply.updated_at.isoformat.return_value = "2023-01-01T00:00:00Z"
        mock_reply.html_url = "https://github.com/test/repo/pull/123#discussion_r456"

        mock_pr = create_mock_pr()
        mock_pr.create_review_comment_reply.return_value = mock_reply
        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            result = manager.reply_to_review_comment(123, 456, "Thanks, fixed.")

            assert result["id"] == 456
            assert result["body"] == "Thanks, fixed."
            assert result["user"] == "testuser"
            assert result["created_at"] == "2023-01-01T00:00:00Z"
            assert result["updated_at"] == "2023-01-01T00:00:00Z"
            assert (
                result["url"] == "https://github.com/test/repo/pull/123#discussion_r456"
            )
            mock_repo.get_pull.assert_called_once_with(123)
            mock_pr.create_review_comment_reply.assert_called_once_with(
                456, "Thanks, fixed."
            )

    def test_reply_to_review_comment_invalid_pr_number(self, tmp_path: Path) -> None:
        """Test that invalid PR number returns empty CommentData with no API call."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            result = manager.reply_to_review_comment(0, 456, "Thanks, fixed.")
            assert result["id"] == 0

    def test_reply_to_review_comment_invalid_comment_id(self, tmp_path: Path) -> None:
        """Test that invalid comment ID returns empty CommentData with no API call."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            result = manager.reply_to_review_comment(123, 0, "Thanks, fixed.")
            assert result["id"] == 0

            result = manager.reply_to_review_comment(123, -1, "Thanks, fixed.")
            assert result["id"] == 0

    @pytest.mark.parametrize("body", ["", "   "])
    def test_reply_to_review_comment_empty_body(
        self, tmp_path: Path, body: str
    ) -> None:
        """Test that empty/whitespace body returns empty CommentData with no API call."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            result = manager.reply_to_review_comment(123, 456, body)
            assert result["id"] == 0

    @patch("mcp_workspace.github_operations._client.Github")
    def test_reply_to_review_comment_repository_unavailable(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Test that an unavailable repository returns empty CommentData."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_github_client = MagicMock()
        mock_github_client.get_repo.side_effect = GithubException(
            404, {"message": "Not Found"}, None
        )
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            result = manager.reply_to_review_comment(123, 456, "Thanks, fixed.")
            assert result["id"] == 0
