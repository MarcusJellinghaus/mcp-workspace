"""Tests for CIResultsManager foundation - initialization and validation."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_workspace.github_operations import CIResultsManager, CIStatusData


class TestCIResultsManagerFoundation:
    """Test the foundational components of CIResultsManager."""

    def test_initialization_with_project_dir(self, tmp_path: Path) -> None:
        """Test initialization with project_dir parameter."""
        # Create a git repository
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Mock the git repository check
        with patch("mcp_workspace.git_operations.is_git_repository", return_value=True):
            # Mock user config to return a token
            with patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="test_token",
            ):
                # Mock Github client
                with patch("github.Github"):
                    manager = CIResultsManager(project_dir=repo_dir)

                    assert manager.project_dir == repo_dir

    def test_initialization_with_repo_url(self) -> None:
        """Test initialization with repo_url parameter."""
        repo_url = "https://github.com/test/repo.git"

        # Mock user config to return a token
        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="test_token",
        ):
            # Mock Github client
            with patch("github.Github"):
                manager = CIResultsManager(repo_url=repo_url)

                assert manager.project_dir is None
                assert manager._cached_repo_identifier.owner == "test"
                assert manager._cached_repo_identifier.repo_name == "repo"
                assert manager._cached_repo_identifier.full_name == "test/repo"

    def test_initialization_validation(self) -> None:
        """Test initialization parameter validation."""
        # Test with neither parameter
        with pytest.raises(
            ValueError, match="Exactly one of project_dir or repo_url must be provided"
        ):
            CIResultsManager()

        # Test with both parameters
        with pytest.raises(
            ValueError, match="Exactly one of project_dir or repo_url must be provided"
        ):
            CIResultsManager(
                project_dir=Path("/tmp"), repo_url="https://github.com/test/repo.git"
            )

    def test_validate_branch_name(self) -> None:
        """Test branch name validation."""
        repo_url = "https://github.com/test/repo.git"

        # Mock user config and Github client
        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="test_token",
        ):
            with patch("github.Github"):
                manager = CIResultsManager(repo_url=repo_url)

                # Valid branch names
                assert manager._validate_branch_name("feature/xyz") is True
                assert manager._validate_branch_name("main") is True
                assert manager._validate_branch_name("develop") is True

                # Invalid branch names
                assert manager._validate_branch_name("") is False
                assert manager._validate_branch_name("   ") is False
                assert (
                    manager._validate_branch_name("branch~1") is False
                )  # Invalid char
                assert (
                    manager._validate_branch_name("branch^2") is False
                )  # Invalid char
                assert (
                    manager._validate_branch_name("branch:fix") is False
                )  # Invalid char
                assert (
                    manager._validate_branch_name("branch?test") is False
                )  # Invalid char
                assert (
                    manager._validate_branch_name("branch*glob") is False
                )  # Invalid char
                assert (
                    manager._validate_branch_name("branch[1]") is False
                )  # Invalid char

    def test_validate_run_id(self) -> None:
        """Test workflow run ID validation."""
        repo_url = "https://github.com/test/repo.git"

        # Mock user config and Github client
        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="test_token",
        ):
            with patch("github.Github"):
                manager = CIResultsManager(repo_url=repo_url)

                # Valid run IDs
                assert manager._validate_run_id(12345) is True
                assert manager._validate_run_id(1) is True
                assert manager._validate_run_id(999999999) is True

                # Invalid run IDs
                assert manager._validate_run_id(0) is False
                assert manager._validate_run_id(-1) is False
                assert manager._validate_run_id(-100) is False

    def test_cistatus_data_structure(self) -> None:
        """Test that CIStatusData TypedDict is properly defined and importable."""
        # Create a test instance to verify structure
        test_data: CIStatusData = {
            "run": {
                "run_ids": [123],
                "status": "completed",
                "conclusion": "failure",
                "workflow_name": "CI",
                "event": "push",
                "workflow_path": ".github/workflows/ci.yml",
                "branch": "main",
                "commit_sha": "abc123",
                "created_at": "2023-01-01T00:00:00Z",
                "url": "https://github.com/test/repo/actions/runs/123",
            },
            "jobs": [
                {
                    "id": 456,
                    "run_id": 123,
                    "name": "test",
                    "status": "completed",
                    "conclusion": "failure",
                    "started_at": "2023-01-01T00:01:00Z",
                    "completed_at": "2023-01-01T00:05:00Z",
                    "steps": [],
                    "html_url": "https://github.com/test/repo/actions/runs/123/job/456",
                    "run_html_url": "https://github.com/test/repo/actions/runs/123",
                    "run_event": "push",
                }
            ],
        }

        # Verify the structure is accessible
        assert test_data["run"]["run_ids"] == [123]
        assert test_data["jobs"][0]["name"] == "test"
        assert len(test_data["jobs"]) == 1

    def test_github_token_passthrough(self) -> None:
        """Test that github_token is forwarded to BaseGitHubManager."""
        repo_url = "https://github.com/test/repo.git"
        with patch("github.Github"):
            manager = CIResultsManager(repo_url=repo_url, github_token="explicit-token")
            assert manager.github_token == "explicit-token"

    def test_manager_inheritance(self) -> None:
        """Test that CIResultsManager properly extends BaseGitHubManager."""
        repo_url = "https://github.com/test/repo.git"

        # Mock user config and Github client
        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="test_token",
        ):
            with patch("github.Github"):
                manager = CIResultsManager(repo_url=repo_url)

                # Verify inheritance - should have BaseGitHubManager attributes
                assert hasattr(manager, "_github_client")
                assert hasattr(manager, "_repository")
                assert hasattr(manager, "_get_repository")
                assert manager._cached_repo_identifier.full_name == "test/repo"
