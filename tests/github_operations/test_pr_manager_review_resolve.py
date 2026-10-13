"""Tests for PullRequestManager.resolve_review_thread() method.

Tests resolving a PR review thread via the resolveReviewThread GraphQL
mutation, using a mocked GraphQL requester.
"""

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import git
import pytest

from mcp_workspace.github_operations.pr_manager import PullRequestManager


@pytest.mark.git_integration
class TestResolveReviewThread:
    """Tests for resolve_review_thread() method."""

    def _setup_resolve_graphql_mock(
        self, manager: "PullRequestManager", side_effect: list[tuple[Any, Any]]
    ) -> Mock:
        """Set up a GraphQL mock on the manager, returning the mock callable."""
        mock_repo = Mock()
        manager._repository = mock_repo  # pylint: disable=protected-access

        manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            side_effect=side_effect
        )
        return manager._github_client._Github__requester.graphql_query  # type: ignore[attr-defined,no-any-return]

    def test_resolve_review_thread_success(self, tmp_path: Path) -> None:
        """Lookup matches PR and is unresolved → mutation runs once, returns True."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        lookup_response = {
            "data": {"node": {"isResolved": False, "pullRequest": {"number": 123}}}
        }
        mutation_response = {
            "data": {"resolveReviewThread": {"thread": {"isResolved": True}}}
        }

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            mock_query = self._setup_resolve_graphql_mock(
                manager, [({}, lookup_response), ({}, mutation_response)]
            )

            result = manager.resolve_review_thread(123, "thread-abc")

            assert result is True
            assert mock_query.call_count == 2

    def test_resolve_review_thread_not_found(self, tmp_path: Path) -> None:
        """node is None → raises ValueError mentioning 'not found'; no mutation."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        lookup_response = {"data": {"node": None}}

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            mock_query = self._setup_resolve_graphql_mock(
                manager, [({}, lookup_response)]
            )

            with pytest.raises(ValueError, match="not found"):
                manager.resolve_review_thread(123, "thread-abc")

            assert mock_query.call_count == 1

    def test_resolve_review_thread_wrong_pr(self, tmp_path: Path) -> None:
        """Thread belongs to a different PR → raises ValueError; no mutation."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        lookup_response = {
            "data": {"node": {"isResolved": False, "pullRequest": {"number": 999}}}
        }

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            mock_query = self._setup_resolve_graphql_mock(
                manager, [({}, lookup_response)]
            )

            with pytest.raises(ValueError, match="does not belong"):
                manager.resolve_review_thread(123, "thread-abc")

            assert mock_query.call_count == 1

    def test_resolve_review_thread_already_resolved(self, tmp_path: Path) -> None:
        """Thread already resolved → raises ValueError; no mutation."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        lookup_response = {
            "data": {"node": {"isResolved": True, "pullRequest": {"number": 123}}}
        }

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            mock_query = self._setup_resolve_graphql_mock(
                manager, [({}, lookup_response)]
            )

            with pytest.raises(ValueError, match="already resolved"):
                manager.resolve_review_thread(123, "thread-abc")

            assert mock_query.call_count == 1

    def test_resolve_review_thread_invalid_pr_number(self, tmp_path: Path) -> None:
        """Invalid pr_number returns False with no GraphQL call at all."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            mock_query = self._setup_resolve_graphql_mock(manager, [])

            assert manager.resolve_review_thread(0, "thread-abc") is False
            mock_query.assert_not_called()

    def test_resolve_review_thread_invalid_thread_id(self, tmp_path: Path) -> None:
        """Empty thread_id raises ValueError with no GraphQL call at all."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            mock_query = self._setup_resolve_graphql_mock(manager, [])

            with pytest.raises(ValueError, match="non-empty string"):
                manager.resolve_review_thread(123, "   ")

            mock_query.assert_not_called()
