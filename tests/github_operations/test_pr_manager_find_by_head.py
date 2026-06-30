"""Tests for PullRequestManager.find_pull_request_by_head() method.

Tests PR discovery by head branch name using mocked GitHub API.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.pr_manager import PullRequestManager

from .test_pr_manager import create_mock_pr


@pytest.mark.git_integration
class TestFindPullRequestByHead:
    """Tests for find_pull_request_by_head() method."""

    @patch("mcp_workspace.github_operations._client.Github")
    def test_find_pr_by_head_success(self, mock_github: Mock, tmp_path: Path) -> None:
        """Single PR found — verify API called with head='owner:branch', returns list with 1 item."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testowner/testrepo.git")

        mock_pr = create_mock_pr(
            number=42,
            title="Feature PR",
            head_ref="feature/xyz",
            base_ref="main",
        )
        mock_repo = MagicMock()
        mock_repo.get_pulls.return_value = [mock_pr]
        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            result = manager.find_pull_request_by_head("feature/xyz")

            assert len(result) == 1
            assert result[0]["number"] == 42
            assert result[0]["title"] == "Feature PR"
            assert result[0]["head_branch"] == "feature/xyz"
            assert result[0]["base_branch"] == "main"
            assert result[0]["mergeable_state"] == "clean"
            mock_repo.get_pulls.assert_called_once_with(
                state="open", head="testowner:feature/xyz"
            )

    @patch("mcp_workspace.github_operations._client.Github")
    def test_find_pr_by_head_multiple_prs(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Two PRs found — returns list with 2 items."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testowner/testrepo.git")

        mock_pr1 = create_mock_pr(number=10, title="PR One", head_ref="feature/abc")
        mock_pr2 = create_mock_pr(number=11, title="PR Two", head_ref="feature/abc")
        mock_repo = MagicMock()
        mock_repo.get_pulls.return_value = [mock_pr1, mock_pr2]
        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            result = manager.find_pull_request_by_head("feature/abc")

            assert len(result) == 2
            assert result[0]["number"] == 10
            assert result[1]["number"] == 11

    @patch("mcp_workspace.github_operations._client.Github")
    def test_find_pr_by_head_not_found(self, mock_github: Mock, tmp_path: Path) -> None:
        """No PRs — returns empty list."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testowner/testrepo.git")

        mock_repo = MagicMock()
        mock_repo.get_pulls.return_value = []
        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            result = manager.find_pull_request_by_head("nonexistent-branch")

            assert result == []

    def test_find_pr_by_head_invalid_branch(self, tmp_path: Path) -> None:
        """Invalid branch name — returns empty list (validation)."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testowner/testrepo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            result = manager.find_pull_request_by_head("invalid~branch")

            assert result == []

    @patch("mcp_workspace.github_operations._client.Github")
    def test_find_pr_by_head_api_error(self, mock_github: Mock, tmp_path: Path) -> None:
        """GithubException — returns empty list (decorator handles)."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testowner/testrepo.git")

        mock_repo = MagicMock()
        mock_repo.get_pulls.side_effect = GithubException(
            500, {"message": "Internal Server Error"}, None
        )
        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            result = manager.find_pull_request_by_head("feature/xyz")

            assert result == []
