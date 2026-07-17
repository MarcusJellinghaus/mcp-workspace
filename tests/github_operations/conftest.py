"""Shared fixtures for GitHub operations tests."""

import io
import zipfile
from pathlib import Path
from typing import Generator
from unittest.mock import Mock, patch

import git
import pytest

from mcp_workspace.github_operations import CIResultsManager
from mcp_workspace.github_operations._network import _reset_network_diagnostics_guard
from mcp_workspace.github_operations.issues import CacheData, IssueData, IssueManager


@pytest.fixture(autouse=True)
def reset_network_diagnostics_guard() -> Generator[None, None, None]:
    """Reset the once-per-process network-diagnostics guard for test isolation."""
    _reset_network_diagnostics_guard()
    yield
    _reset_network_diagnostics_guard()


@pytest.fixture
def mock_repo() -> Mock:
    """Mock GitHub repository for testing."""
    return Mock()


@pytest.fixture
def ci_manager(mock_repo: Mock) -> CIResultsManager:
    """CIResultsManager instance for testing with mocked dependencies."""
    repo_url = "https://github.com/test/repo.git"

    with patch(
        "mcp_workspace.github_operations.base_manager.get_github_token",
        return_value="test_token",
    ):
        with patch("github.Github") as mock_github:
            mock_github.return_value.get_repo.return_value = mock_repo
            manager = CIResultsManager(repo_url=repo_url)
            manager._repository = mock_repo
            return manager


@pytest.fixture
def mock_artifact() -> Mock:
    """Mock artifact for testing."""
    artifact = Mock()
    artifact.name = "test-results"
    artifact.archive_download_url = (
        "https://api.github.com/repos/test/repo/artifacts/123/zip"
    )
    return artifact


@pytest.fixture
def mock_zip_content() -> bytes:
    """Create mock ZIP content with test files."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("results.xml", "<?xml version='1.0'?><testsuites></testsuites>")
        zf.writestr("coverage.json", '{"total": 85.5}')
    return buffer.getvalue()


# Issue cache fixtures


@pytest.fixture
def sample_issue() -> IssueData:
    """Sample issue data for testing."""
    return {
        "number": 123,
        "state": "open",
        "labels": ["status-02:awaiting-planning"],
        "updated_at": "2025-12-31T09:00:00Z",
        "url": "https://github.com/test/repo/issues/123",
        "title": "Test issue",
        "body": "Test issue body",
        "assignees": [],
        "user": "testuser",
        "created_at": "2025-12-31T08:00:00Z",
        "locked": False,
    }


@pytest.fixture
def sample_cache_data() -> CacheData:
    """Sample cache data structure."""
    return {
        "last_checked": "2025-12-31T10:30:00Z",
        "last_full_refresh": "2025-12-31T10:30:00Z",
        "updates_covered_through": "2025-12-31T09:00:00Z",
        "issues": {
            "123": {
                "number": 123,
                "state": "open",
                "labels": ["status-02:awaiting-planning"],
                "updated_at": "2025-12-31T09:00:00Z",
                "url": "https://github.com/test/repo/issues/123",
                "title": "Test issue",
                "body": "Test issue body",
                "assignees": [],
                "user": "testuser",
                "created_at": "2025-12-31T08:00:00Z",
                "locked": False,
            }
        },
    }


@pytest.fixture
def mock_cache_issue_manager() -> Mock:
    """Mock IssueManager for cache testing."""
    manager = Mock()
    manager.list_issues.return_value = []
    # _fetch_and_merge_issues calls _list_issues_no_error_handling (not list_issues).
    # Share the same Mock so existing tests that set list_issues.return_value still work.
    manager._list_issues_no_error_handling = manager.list_issues
    return manager


@pytest.fixture
def mock_issue_manager(tmp_path: Path) -> Generator[IssueManager, None, None]:
    """Create a real IssueManager with mocked GitHub API for unit testing.

    This fixture creates a real IssueManager instance with:
    - A temporary git repository
    - Mocked GitHub API client and repository
    - All IssueManager logic runs normally, only GitHub API calls are mocked

    This allows tests to verify that IssueManager correctly transforms
    GitHub API responses into IssueData/CommentData/EventData structures.

    Tests access the mocked repository via manager._repository attribute.
    """
    # Create temporary git directory
    git_dir = tmp_path / "test_repo"
    git_dir.mkdir()
    repo = git.Repo.init(git_dir)
    repo.create_remote("origin", "https://github.com/test/repo.git")

    # Patch GitHub client and config
    with patch(
        "mcp_workspace.github_operations.base_manager.get_github_token",
        return_value="test-token",
    ):
        with patch(
            "mcp_workspace.github_operations.base_manager.Github"
        ) as mock_github:
            mock_repo_obj = Mock()
            mock_github_client = Mock()
            mock_github_client.get_repo.return_value = mock_repo_obj
            mock_github.return_value = mock_github_client

            # Create real IssueManager instance
            manager = IssueManager(git_dir)

            # Store mocked repository for test access
            # Note: _repository is Optional, so tests must assert it's not None before use
            # or accept union-attr warnings from mypy
            manager._repository = mock_repo_obj

            yield manager
