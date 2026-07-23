"""Comprehensive unit tests for PullRequestManager with mocked GitHub API.

This module focuses on testing our wrapper logic, validation, error handling,
and data transformation - NOT the PyGithub library itself.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.pr_manager import PullRequestManager


def create_mock_pr(**overrides: Any) -> MagicMock:
    """Create a mock PR object with common defaults."""
    mock_pr = MagicMock()
    mock_pr.number = overrides.get("number", 123)
    mock_pr.title = overrides.get("title", "Test PR")
    mock_pr.body = overrides.get("body", "Test description")
    mock_pr.state = overrides.get("state", "open")
    mock_pr.head.ref = overrides.get("head_ref", "feature-branch")
    mock_pr.base.ref = overrides.get("base_ref", "main")
    mock_pr.html_url = overrides.get(
        "url", f"https://github.com/test/repo/pull/{mock_pr.number}"
    )
    mock_pr.mergeable = overrides.get("mergeable", True)
    mock_pr.mergeable_state = overrides.get("mergeable_state", "clean")
    mock_pr.merged = overrides.get("merged", False)
    mock_pr.draft = overrides.get("draft", False)
    # Handle optional datetime fields
    if overrides.get("created_at") is None and "skip_dates" not in overrides:
        mock_pr.created_at.isoformat.return_value = "2023-01-01T00:00:00Z"
    elif overrides.get("created_at"):
        mock_pr.created_at.isoformat.return_value = overrides["created_at"]
    else:
        mock_pr.created_at = None
    if overrides.get("updated_at") is None and "skip_dates" not in overrides:
        mock_pr.updated_at.isoformat.return_value = "2023-01-01T00:00:00Z"
    elif overrides.get("updated_at"):
        mock_pr.updated_at.isoformat.return_value = overrides["updated_at"]
    else:
        mock_pr.updated_at = None
    # Handle user
    if overrides.get("user") is None and "skip_user" not in overrides:
        mock_pr.user.login = overrides.get("user_login", "testuser")
    else:
        mock_pr.user = overrides.get("user")
    # Handle assignees (list of NamedUser-like objects with .login).
    # Default [] keeps existing tests green (an unconfigured MagicMock
    # would not be iterable in [a.login for a in pr.assignees]).
    mock_pr.assignees = overrides.get("assignees", [])
    return mock_pr


@pytest.mark.git_integration
class TestPullRequestManagerUnit:
    """Unit tests for PullRequestManager with mocked dependencies."""

    # ========================================
    # Initialization Tests
    # ========================================

    def test_initialization_requires_project_dir(self) -> None:
        """Test that None project_dir raises ValueError."""
        with pytest.raises(
            ValueError, match="Exactly one of project_dir or repo_url must be provided"
        ):
            PullRequestManager(None)

    def test_initialization_requires_git_repository(self, tmp_path: Path) -> None:
        """Test that non-git directory raises ValueError."""
        regular_dir = tmp_path / "regular_dir"
        regular_dir.mkdir()

        with pytest.raises(ValueError, match="Directory is not a git repository"):
            PullRequestManager(regular_dir)

    def test_initialization_requires_github_remote(self, tmp_path: Path) -> None:
        """Test that git repo without GitHub remote raises ValueError."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        git.Repo.init(git_dir)  # No remote configured

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            with pytest.raises(
                ValueError, match="Could not detect GitHub repository URL"
            ):
                PullRequestManager(git_dir)

    def test_initialization_requires_github_token(self, tmp_path: Path) -> None:
        """Test that missing GitHub token raises ValueError."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value=None,
        ):
            with pytest.raises(ValueError, match="GitHub token not found"):
                PullRequestManager(git_dir)

    # ========================================
    # Validation Tests
    # ========================================

    def test_validate_pr_number(self, tmp_path: Path) -> None:
        """Test PR number validation logic."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            # Valid PR numbers
            assert manager._validate_pr_number(1) is True
            assert manager._validate_pr_number(123) is True
            assert manager._validate_pr_number(99999) is True

            # Invalid PR numbers
            assert manager._validate_pr_number(0) is False
            assert manager._validate_pr_number(-1) is False
            assert manager._validate_pr_number(-999) is False

    def test_validate_branch_name(self, tmp_path: Path) -> None:
        """Test branch name validation logic."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            # Valid branch names
            assert manager._validate_branch_name("main") is True
            assert manager._validate_branch_name("feature-branch") is True
            assert manager._validate_branch_name("feature/new-feature") is True
            assert manager._validate_branch_name("bugfix_123") is True

            # Invalid branch names - empty or whitespace
            assert manager._validate_branch_name("") is False
            assert manager._validate_branch_name("   ") is False

            # Invalid branch names - invalid characters
            assert manager._validate_branch_name("branch~name") is False
            assert manager._validate_branch_name("branch^name") is False
            assert manager._validate_branch_name("branch:name") is False
            assert manager._validate_branch_name("branch?name") is False
            assert manager._validate_branch_name("branch*name") is False
            assert manager._validate_branch_name("branch[name") is False

            # Invalid branch names - invalid start/end
            assert manager._validate_branch_name(".branch") is False
            assert manager._validate_branch_name("branch.") is False
            assert manager._validate_branch_name("branch.lock") is False

    # ========================================
    # Property Tests
    # ========================================

    def test_repository_name_property(self, tmp_path: Path) -> None:
        """Test repository_name property returns correct format."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testuser/testrepo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="test-token",
        ):
            manager = PullRequestManager(git_dir)

            assert manager.repository_name == "testuser/testrepo"

    def test_repo_identifier_property(self, tmp_path: Path) -> None:
        """Test _repo_identifier is set correctly from git remote."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testuser/testrepo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="test-token",
        ):
            manager = PullRequestManager(git_dir)

            assert manager._repo_identifier.full_name == "testuser/testrepo"
            assert manager._repo_identifier.hostname == "github.com"
            assert (
                manager._repo_identifier.https_url
                == "https://github.com/testuser/testrepo"
            )

    # ========================================
    # Create Pull Request Tests
    # ========================================

    @patch("mcp_workspace.github_operations._client.Github")
    def test_create_pull_request_success(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Test successful PR creation with mocked GitHub API."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_pr = create_mock_pr()
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
                "Test PR", "feature-branch", "main", "Test description"
            )
            assert result["number"] == 123
            assert result["title"] == "Test PR"
            assert result["body"] == "Test description"
            assert result["state"] == "open"
            assert result["head_branch"] == "feature-branch"
            assert result["base_branch"] == "main"
            assert result["url"] == "https://github.com/test/repo/pull/123"
            assert result["mergeable_state"] == "clean"
            mock_repo.create_pull.assert_called_once_with(
                title="Test PR",
                body="Test description",
                head="feature-branch",
                base="main",
            )

    def test_create_pull_request_empty_title(self, tmp_path: Path) -> None:
        """Test that empty title returns empty dict."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            # Empty title
            result = manager.create_pull_request("", "feature-branch", "main")
            assert not result

            # Whitespace-only title
            result = manager.create_pull_request("   ", "feature-branch", "main")
            assert not result

    def test_create_pull_request_invalid_head_branch(self, tmp_path: Path) -> None:
        """Test that invalid head branch returns empty dict."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            result = manager.create_pull_request(
                "Valid Title", "invalid~branch", "main"
            )
            assert not result

    def test_create_pull_request_invalid_base_branch(self, tmp_path: Path) -> None:
        """Test that invalid base branch returns empty dict."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            result = manager.create_pull_request(
                "Valid Title", "feature", "invalid^branch"
            )
            assert not result

    # ========================================
    # Get Pull Request Tests
    # ========================================

    @patch("mcp_workspace.github_operations._client.Github")
    def test_get_pull_request_success(self, mock_github: Mock, tmp_path: Path) -> None:
        """Test successful PR retrieval."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

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
            result = manager.get_pull_request(123)
            assert result["number"] == 123
            assert result["title"] == "Test PR"
            assert result["mergeable_state"] == "clean"
            assert result["assignees"] == []
            mock_repo.get_pull.assert_called_once_with(123)

    def test_get_pull_request_invalid_number(self, tmp_path: Path) -> None:
        """Test that invalid PR number returns empty dict."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            result = manager.get_pull_request(-1)
            assert not result

            result = manager.get_pull_request(0)
            assert not result

    @patch("mcp_workspace.github_operations._client.Github")
    def test_assignees_serialized_across_methods(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Assignees flatten to logins on both get_pull_request and list_pull_requests."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_pr = create_mock_pr(
            assignees=[MagicMock(login="alice"), MagicMock(login="bob")]
        )
        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_pulls.return_value = [mock_pr]
        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            get_result = manager.get_pull_request(123)
            assert get_result["assignees"] == ["alice", "bob"]

            list_result = manager.list_pull_requests(state="open")
            assert list_result[0]["assignees"] == ["alice", "bob"]

    # ========================================
    # List Pull Requests Tests
    # ========================================

    @patch("mcp_workspace.github_operations._client.Github")
    def test_list_pull_requests_data_transformation(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Test that our wrapper correctly transforms PyGithub objects to our format."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_pr1 = create_mock_pr(
            number=1,
            title="First PR",
            body="First description",
            head_ref="feature-1",
            user_login="user1",
        )
        mock_pr2 = create_mock_pr(
            number=2,
            title="Second PR",
            body="Second description",
            head_ref="feature-2",
            user_login="user2",
            mergeable=False,
            mergeable_state="dirty",
            draft=True,
            created_at="2023-01-02T00:00:00Z",
            updated_at="2023-01-02T00:00:00Z",
        )
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
            result = manager.list_pull_requests(state="open")
            assert len(result) == 2
            assert result[0]["number"] == 1
            assert result[0]["title"] == "First PR"
            assert result[0]["draft"] is False
            assert result[0]["mergeable_state"] == "clean"
            assert result[1]["number"] == 2
            assert result[1]["title"] == "Second PR"
            assert result[1]["draft"] is True
            assert result[1]["mergeable_state"] == "dirty"
            mock_repo.get_pulls.assert_called_once_with(state="open")

    @patch("mcp_workspace.github_operations._client.Github")
    def test_list_pull_requests_with_base_branch_filter(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Test listing PRs with base branch filter."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

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

            manager.list_pull_requests(state="all", base_branch="develop")

            # Verify API was called with base branch parameter
            mock_repo.get_pulls.assert_called_once_with(state="all", base="develop")

    def test_list_pull_requests_invalid_base_branch(self, tmp_path: Path) -> None:
        """Test that invalid base branch returns empty list."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            result = manager.list_pull_requests(base_branch="invalid~branch")
            assert result == []

    # ========================================
    # Close Pull Request Tests
    # ========================================

    @patch("mcp_workspace.github_operations._client.Github")
    def test_close_pull_request_success(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Test successful PR closing."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_pr = create_mock_pr(state="closed", updated_at="2023-01-01T01:00:00Z")
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
            result = manager.close_pull_request(123)
            assert result["number"] == 123
            assert result["state"] == "closed"
            assert result["mergeable_state"] == "clean"
            mock_pr.edit.assert_called_once_with(state="closed")
            assert mock_repo.get_pull.call_count == 2

    def test_close_pull_request_invalid_number(self, tmp_path: Path) -> None:
        """Test closing PR with invalid number."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            result = manager.close_pull_request(0)
            assert not result

            result = manager.close_pull_request(-1)
            assert not result

    # ========================================
    # Error Handling Tests
    # ========================================

    @patch("mcp_workspace.github_operations._client.Github")
    def test_github_api_error_returns_empty(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Test that GitHub API errors are handled gracefully."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        # Mock API to raise error
        mock_repo = MagicMock()
        mock_repo.create_pull.side_effect = GithubException(
            404, {"message": "Not Found"}, None
        )

        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            # Errors should return empty dict
            result = manager.create_pull_request("Test PR", "feature", "main")
            assert not result


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
