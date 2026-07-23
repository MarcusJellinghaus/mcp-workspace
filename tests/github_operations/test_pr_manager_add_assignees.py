"""Tests for PullRequestManager.add_assignees() method.

Tests adding assignees to a pull request using mocked GitHub API.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.pr_manager import PullRequestManager

from ._pr_test_helpers import create_mock_pr


@pytest.mark.git_integration
class TestAddAssignees:
    """Tests for add_assignees() method."""

    @patch("mcp_workspace.github_operations._client.Github")
    def test_add_assignees_success(self, mock_github: Mock, tmp_path: Path) -> None:
        """Happy path — single login assigned, mutated assignees reflected in result."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testowner/testrepo.git")

        mock_pr = create_mock_pr(assignees=[MagicMock(login="alice")])
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
            result = manager.add_assignees(123, "alice")

            mock_pr.add_to_assignees.assert_called_once_with("alice")
            assert result["assignees"] == ["alice"]

    @patch("mcp_workspace.github_operations._client.Github")
    def test_add_assignees_multiple_logins(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Multiple logins — add_to_assignees called once with all logins."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testowner/testrepo.git")

        mock_pr = create_mock_pr(
            assignees=[MagicMock(login="alice"), MagicMock(login="bob")]
        )
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
            result = manager.add_assignees(123, "alice", "bob")

            mock_pr.add_to_assignees.assert_called_once_with("alice", "bob")
            assert result["assignees"] == ["alice", "bob"]

    @patch("mcp_workspace.github_operations._client.Github")
    def test_add_assignees_empty_logins(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Empty logins — no API write, returns current PR data."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testowner/testrepo.git")

        mock_pr = create_mock_pr()
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
            result = manager.add_assignees(123)

            mock_pr.add_to_assignees.assert_not_called()
            assert result["number"] == 123

    @patch("mcp_workspace.github_operations._client.Github")
    def test_add_assignees_invalid_pr_number(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Invalid pr_number — returns empty dict, get_pull not called."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testowner/testrepo.git")

        mock_repo = MagicMock()
        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            result = manager.add_assignees(0, "alice")

            assert not result  # empty dict
            mock_repo.get_pull.assert_not_called()

    @patch("mcp_workspace.github_operations._client.Github")
    def test_add_assignees_api_error(self, mock_github: Mock, tmp_path: Path) -> None:
        """GithubException — returns empty dict (decorator handles)."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testowner/testrepo.git")

        mock_repo = MagicMock()
        mock_repo.get_pull.side_effect = GithubException(
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
            result = manager.add_assignees(123, "alice")

            assert not result  # empty dict
