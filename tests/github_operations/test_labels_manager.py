"""Comprehensive unit tests for LabelsManager with mocked GitHub API.

This module focuses on testing our wrapper logic, validation, error handling,
and data transformation - NOT the PyGithub library itself.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.labels_manager import LabelsManager


@pytest.mark.git_integration
class TestLabelsManagerUnit:
    """Unit tests for LabelsManager with mocked dependencies."""

    # ========================================
    # Initialization Tests
    # ========================================

    def test_initialization_requires_project_dir(self) -> None:
        """Test that None project_dir raises ValueError."""
        with pytest.raises(
            ValueError, match="Exactly one of project_dir or repo_url must be provided"
        ):
            LabelsManager(None)

    def test_initialization_requires_git_repository(self, tmp_path: Path) -> None:
        """Test that non-git directory raises ValueError."""
        regular_dir = tmp_path / "regular_dir"
        regular_dir.mkdir()

        with pytest.raises(ValueError, match="Directory is not a git repository"):
            LabelsManager(regular_dir)

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
                LabelsManager(git_dir)

    # ========================================
    # Validation Tests
    # ========================================

    def test_validate_label_name(self, tmp_path: Path) -> None:
        """Test label name validation logic."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            # Valid names
            assert manager._validate_label_name("bug") is True
            assert manager._validate_label_name("feature-request") is True
            assert manager._validate_label_name("high priority") is True
            assert manager._validate_label_name("bug :bug:") is True
            assert manager._validate_label_name("type/enhancement") is True

            # Invalid names - empty or whitespace
            assert manager._validate_label_name("") is False
            assert manager._validate_label_name("   ") is False

            # Invalid names - leading/trailing whitespace
            assert manager._validate_label_name("  leading") is False
            assert manager._validate_label_name("trailing  ") is False

    def test_validate_color(self, tmp_path: Path) -> None:
        """Test color validation logic."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            # Valid colors
            assert manager._validate_color("FF0000") is True
            assert manager._validate_color("#FF0000") is True
            assert manager._validate_color("00ff00") is True
            assert manager._validate_color("#00FF00") is True
            assert manager._validate_color("ABC123") is True

            # Invalid colors
            assert manager._validate_color("red") is False
            assert manager._validate_color("12345") is False  # Too short
            assert manager._validate_color("GGGGGG") is False  # Invalid hex
            assert manager._validate_color("#12345") is False  # Too short
            assert manager._validate_color("") is False
            assert manager._validate_color("#") is False

    def test_normalize_color(self, tmp_path: Path) -> None:
        """Test color normalization (removing # prefix)."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            assert manager._normalize_color("#FF0000") == "FF0000"
            assert manager._normalize_color("FF0000") == "FF0000"
            assert manager._normalize_color("#00ff00") == "00ff00"
            assert manager._normalize_color("00FF00") == "00FF00"

    # ========================================
    # Create Label Tests
    # ========================================

    @patch("mcp_workspace.github_operations._client.Github")
    def test_create_label_success(self, mock_github: Mock, tmp_path: Path) -> None:
        """Test successful label creation."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        # Mock label object
        mock_label = MagicMock()
        mock_label.name = "bug"
        mock_label.color = "d73a4a"
        mock_label.description = "Something isn't working"
        mock_label.url = "https://api.github.com/repos/test/repo/labels/bug"

        mock_repo = MagicMock()
        mock_repo.create_label.return_value = mock_label

        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.create_label("bug", "d73a4a", "Something isn't working")

            assert result["name"] == "bug"
            assert result["color"] == "d73a4a"
            assert result["description"] == "Something isn't working"
            assert result["url"] == "https://api.github.com/repos/test/repo/labels/bug"

            # Verify API was called with normalized color (no #)
            mock_repo.create_label.assert_called_once_with(
                name="bug", color="d73a4a", description="Something isn't working"
            )

    @patch("mcp_workspace.github_operations._client.Github")
    def test_create_label_with_hash_prefix(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Test label creation with # prefix in color is normalized."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_label = MagicMock()
        mock_label.name = "enhancement"
        mock_label.color = "a2eeef"
        mock_label.description = "New feature"
        mock_label.url = "https://api.github.com/repos/test/repo/labels/enhancement"

        mock_repo = MagicMock()
        mock_repo.create_label.return_value = mock_label

        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.create_label("enhancement", "#a2eeef", "New feature")

            assert result["color"] == "a2eeef"

            # Verify color was normalized (# removed)
            mock_repo.create_label.assert_called_once_with(
                name="enhancement", color="a2eeef", description="New feature"
            )

    def test_create_label_invalid_name(self, tmp_path: Path) -> None:
        """Test that invalid label name returns empty dict."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.create_label("", "FF0000", "Description")
            assert not result

            result = manager.create_label("   ", "FF0000", "Description")
            assert not result

    def test_create_label_invalid_color(self, tmp_path: Path) -> None:
        """Test that invalid color returns empty dict."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.create_label("bug", "red", "Description")
            assert not result

            result = manager.create_label("bug", "12345", "Description")
            assert not result

    # ========================================
    # Get Label Tests
    # ========================================

    @patch("mcp_workspace.github_operations._client.Github")
    def test_get_label_success(self, mock_github: Mock, tmp_path: Path) -> None:
        """Test successful label retrieval."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_label = MagicMock()
        mock_label.name = "bug"
        mock_label.color = "d73a4a"
        mock_label.description = "Something isn't working"
        mock_label.url = "https://api.github.com/repos/test/repo/labels/bug"

        mock_repo = MagicMock()
        mock_repo.get_label.return_value = mock_label

        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.get_label("bug")

            assert result["name"] == "bug"
            assert result["color"] == "d73a4a"
            mock_repo.get_label.assert_called_once_with("bug")

    def test_get_label_invalid_name(self, tmp_path: Path) -> None:
        """Test that invalid label name returns empty dict."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.get_label("")
            assert not result

            result = manager.get_label("   ")
            assert not result

    # ========================================
    # Get Labels (List All) Tests
    # ========================================

    @patch("mcp_workspace.github_operations._client.Github")
    def test_get_labels_data_transformation(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Test that our wrapper correctly transforms PyGithub objects to our format."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        # Mock multiple label objects
        mock_label1 = MagicMock()
        mock_label1.name = "bug"
        mock_label1.color = "d73a4a"
        mock_label1.description = "Something isn't working"
        mock_label1.url = "https://api.github.com/repos/test/repo/labels/bug"

        mock_label2 = MagicMock()
        mock_label2.name = "enhancement"
        mock_label2.color = "a2eeef"
        mock_label2.description = "New feature or request"
        mock_label2.url = "https://api.github.com/repos/test/repo/labels/enhancement"

        mock_label3 = MagicMock()
        mock_label3.name = "documentation"
        mock_label3.color = "0075ca"
        mock_label3.description = ""
        mock_label3.url = "https://api.github.com/repos/test/repo/labels/documentation"

        mock_repo = MagicMock()
        mock_repo.get_labels.return_value = [mock_label1, mock_label2, mock_label3]

        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.get_labels()

            # Verify we got 3 labels
            assert len(result) == 3

            # Verify data transformation is correct
            assert result[0]["name"] == "bug"
            assert result[0]["color"] == "d73a4a"
            assert result[0]["description"] == "Something isn't working"
            assert result[1]["name"] == "enhancement"
            assert result[1]["color"] == "a2eeef"
            assert result[2]["name"] == "documentation"
            assert result[2]["description"] == ""

            mock_repo.get_labels.assert_called_once()

    # ========================================
    # Update Label Tests
    # ========================================

    @patch("mcp_workspace.github_operations._client.Github")
    def test_update_label_color(self, mock_github: Mock, tmp_path: Path) -> None:
        """Test updating label color."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_label = MagicMock()
        mock_label.name = "bug"
        mock_label.color = "FF0000"  # New color
        mock_label.description = "Something isn't working"
        mock_label.url = "https://api.github.com/repos/test/repo/labels/bug"

        mock_repo = MagicMock()
        mock_repo.get_label.return_value = mock_label

        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.update_label("bug", color="FF0000")

            assert result["name"] == "bug"
            assert result["color"] == "FF0000"

            # Verify edit was called with normalized color
            mock_label.edit.assert_called_once()

    @patch("mcp_workspace.github_operations._client.Github")
    def test_update_label_description(self, mock_github: Mock, tmp_path: Path) -> None:
        """Test updating label description."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_label = MagicMock()
        mock_label.name = "bug"
        mock_label.color = "d73a4a"
        mock_label.description = "Updated description"
        mock_label.url = "https://api.github.com/repos/test/repo/labels/bug"

        mock_repo = MagicMock()
        mock_repo.get_label.return_value = mock_label

        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.update_label("bug", description="Updated description")

            assert result["description"] == "Updated description"
            mock_label.edit.assert_called_once()

    @patch("mcp_workspace.github_operations._client.Github")
    def test_update_label_rename(self, mock_github: Mock, tmp_path: Path) -> None:
        """Test renaming a label."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_old_label = MagicMock()
        mock_old_label.name = "bug"
        mock_old_label.color = "d73a4a"
        mock_old_label.description = "Something isn't working"

        mock_new_label = MagicMock()
        mock_new_label.name = "defect"
        mock_new_label.color = "d73a4a"
        mock_new_label.description = "Something isn't working"
        mock_new_label.url = "https://api.github.com/repos/test/repo/labels/defect"

        mock_repo = MagicMock()
        mock_repo.get_label.side_effect = [mock_old_label, mock_new_label]

        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.update_label("bug", new_name="defect")

            assert result["name"] == "defect"
            mock_old_label.edit.assert_called_once()
            # get_label called twice: once to get old, once to get updated
            assert mock_repo.get_label.call_count == 2

    def test_update_label_invalid_name(self, tmp_path: Path) -> None:
        """Test that invalid label name returns empty dict."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.update_label("", color="FF0000")
            assert not result

            result = manager.update_label("   ", color="FF0000")
            assert not result

    def test_update_label_invalid_new_name(self, tmp_path: Path) -> None:
        """Test that invalid new name returns empty dict."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.update_label("bug", new_name="")
            assert not result

            result = manager.update_label("bug", new_name="   ")
            assert not result

    def test_update_label_invalid_color(self, tmp_path: Path) -> None:
        """Test that invalid color returns empty dict."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.update_label("bug", color="red")
            assert not result

            result = manager.update_label("bug", color="12345")
            assert not result

    # ========================================
    # Delete Label Tests
    # ========================================

    @patch("mcp_workspace.github_operations._client.Github")
    def test_delete_label_success(self, mock_github: Mock, tmp_path: Path) -> None:
        """Test successful label deletion."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_label = MagicMock()

        mock_repo = MagicMock()
        mock_repo.get_label.return_value = mock_label

        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.delete_label("bug")

            assert result is True
            mock_label.delete.assert_called_once()

    def test_delete_label_invalid_name(self, tmp_path: Path) -> None:
        """Test that invalid label name returns False."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            result = manager.delete_label("")
            assert result is False

            result = manager.delete_label("   ")
            assert result is False

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
        mock_repo.create_label.side_effect = GithubException(
            404, {"message": "Not Found"}, None
        )

        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            # Errors should return empty dict
            result = manager.create_label("bug", "FF0000", "Description")
            assert not result
