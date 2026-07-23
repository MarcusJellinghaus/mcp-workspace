"""Unit tests for dynamic default branch resolution in create_pull_request().

This module focuses on testing our wrapper logic for resolving the base branch
when none is provided - NOT the PyGithub library itself.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import git
import pytest

from mcp_workspace.github_operations.pr_manager import PullRequestManager

from ._pr_test_helpers import create_mock_pr


@pytest.mark.git_integration
class TestCreatePullRequestDefaultBranch:
    """Tests for dynamic default branch resolution in create_pull_request()."""

    @patch("mcp_workspace.github_operations._client.Github")
    @patch("mcp_workspace.github_operations.pr_manager.get_default_branch_name")
    def test_create_pr_resolves_default_branch_when_none(
        self, mock_get_default: Mock, mock_github: Mock, tmp_path: Path
    ) -> None:
        """When base_branch=None, resolves via get_default_branch_name()."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_get_default.return_value = "main"
        mock_pr = create_mock_pr(
            number=1,
            body="Body",
            url="https://github.com/test/repo/pull/1",
            skip_dates=True,
            skip_user=True,
        )
        mock_pr.created_at = None
        mock_pr.updated_at = None
        mock_pr.user = None
        mock_repo = MagicMock()
        mock_repo.create_pull.return_value = mock_pr
        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            result = manager.create_pull_request(
                title="Test PR",
                head_branch="feature-branch",
                base_branch=None,
                body="Body",
            )
            mock_get_default.assert_called_once_with(git_dir)
            mock_repo.create_pull.assert_called_once()
            assert mock_repo.create_pull.call_args[1]["base"] == "main"
            assert result["number"] == 1
            assert result["base_branch"] == "main"

    @patch("mcp_workspace.github_operations._client.Github")
    @patch("mcp_workspace.github_operations.pr_manager.get_default_branch_name")
    def test_create_pr_uses_explicit_base_branch(
        self, mock_get_default: Mock, mock_github: Mock, tmp_path: Path
    ) -> None:
        """When base_branch is provided, uses it directly without calling get_default_branch_name()."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_pr = create_mock_pr(
            number=1,
            body="Body",
            base_ref="develop",
            url="https://github.com/test/repo/pull/1",
            skip_dates=True,
            skip_user=True,
        )
        mock_pr.created_at = None
        mock_pr.updated_at = None
        mock_pr.user = None
        mock_repo = MagicMock()
        mock_repo.create_pull.return_value = mock_pr
        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            result = manager.create_pull_request(
                title="Test PR",
                head_branch="feature-branch",
                base_branch="develop",
                body="Body",
            )
            mock_get_default.assert_not_called()
            assert mock_repo.create_pull.call_args[1]["base"] == "develop"
            assert result["number"] == 1
            assert result["base_branch"] == "develop"

    @patch("mcp_workspace.github_operations._client.Github")
    @patch("mcp_workspace.github_operations.pr_manager.get_default_branch_name")
    def test_create_pr_returns_empty_when_default_branch_unknown(
        self, mock_get_default: Mock, mock_github: Mock, tmp_path: Path
    ) -> None:
        """When default branch cannot be determined, returns empty dict."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_get_default.return_value = None  # Cannot determine default branch

        mock_repo = MagicMock()

        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            result = manager.create_pull_request(
                title="Test PR",
                head_branch="feature-branch",
                base_branch=None,
                body="Body",
            )

            # Should return empty dict (falsy)
            assert not result

            # PR creation should not be attempted
            mock_repo.create_pull.assert_not_called()

    @patch("mcp_workspace.github_operations._client.Github")
    @patch("mcp_workspace.github_operations.pr_manager.get_default_branch_name")
    def test_create_pr_resolves_master_as_default_branch(
        self, mock_get_default: Mock, mock_github: Mock, tmp_path: Path
    ) -> None:
        """When default branch is 'master', uses it correctly."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_get_default.return_value = "master"
        mock_pr = create_mock_pr(
            number=1,
            body="Body",
            base_ref="master",
            url="https://github.com/test/repo/pull/1",
            skip_dates=True,
            skip_user=True,
        )
        mock_pr.created_at = None
        mock_pr.updated_at = None
        mock_pr.user = None
        mock_repo = MagicMock()
        mock_repo.create_pull.return_value = mock_pr
        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            result = manager.create_pull_request(
                title="Test PR",
                head_branch="feature-branch",
                base_branch=None,
                body="Body",
            )
            mock_get_default.assert_called_once_with(git_dir)
            assert mock_repo.create_pull.call_args[1]["base"] == "master"
            assert result["number"] == 1
            assert result["base_branch"] == "master"
