"""Unit tests for PullRequestManager.get_closing_issue_numbers() method."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import git
import pytest

from mcp_workspace.github_operations.pr_manager import PullRequestManager


@pytest.mark.git_integration
class TestGetClosingIssueNumbers:
    """Tests for PullRequestManager.get_closing_issue_numbers() method."""

    @pytest.fixture
    def mock_manager(self, tmp_path: Path) -> PullRequestManager:
        """Create a PullRequestManager with mocked dependencies."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            return manager

    def _setup_graphql_mock(
        self, manager: PullRequestManager, response: dict[str, Any]
    ) -> None:
        """Set up GraphQL mock on the manager."""
        mock_repo = Mock()
        mock_repo.owner.login = "test"
        mock_repo.name = "repo"
        manager._repository = mock_repo

        manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, response)
        )

    def test_get_closing_issue_numbers_single_issue(
        self, mock_manager: PullRequestManager
    ) -> None:
        """GraphQL returns one linked issue → returns [92]."""
        response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "closingIssuesReferences": {"nodes": [{"number": 92}]}
                    }
                }
            }
        }
        self._setup_graphql_mock(mock_manager, response)
        result = mock_manager.get_closing_issue_numbers(42)
        assert result == [92]

    def test_get_closing_issue_numbers_multiple_issues(
        self, mock_manager: PullRequestManager
    ) -> None:
        """GraphQL returns two issues → returns [92, 55]."""
        response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "closingIssuesReferences": {
                            "nodes": [{"number": 92}, {"number": 55}]
                        }
                    }
                }
            }
        }
        self._setup_graphql_mock(mock_manager, response)
        result = mock_manager.get_closing_issue_numbers(42)
        assert result == [92, 55]

    def test_get_closing_issue_numbers_no_issues(
        self, mock_manager: PullRequestManager
    ) -> None:
        """GraphQL returns empty nodes → returns []."""
        response: dict[str, Any] = {
            "data": {
                "repository": {
                    "pullRequest": {"closingIssuesReferences": {"nodes": []}}
                }
            }
        }
        self._setup_graphql_mock(mock_manager, response)
        result = mock_manager.get_closing_issue_numbers(42)
        assert result == []

    def test_get_closing_issue_numbers_invalid_pr_number(
        self, mock_manager: PullRequestManager
    ) -> None:
        """pr_number=0 → returns []."""
        result = mock_manager.get_closing_issue_numbers(0)
        assert result == []

    def test_get_closing_issue_numbers_pr_not_found(
        self, mock_manager: PullRequestManager
    ) -> None:
        """GraphQL returns null pullRequest → returns []."""
        response: dict[str, Any] = {"data": {"repository": {"pullRequest": None}}}
        self._setup_graphql_mock(mock_manager, response)
        result = mock_manager.get_closing_issue_numbers(42)
        assert result == []
