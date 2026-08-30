"""Unit tests for IssueBranchManager linked-branch query methods."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from mcp_workspace.github_operations.issues import (
    IssueBranchManager,
)


class TestGetLinkedBranches:
    """Test suite for IssueBranchManager.get_linked_branches() method."""

    @pytest.fixture
    def mock_manager(self) -> IssueBranchManager:
        """Create a mock IssueBranchManager for testing."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with (
            patch("mcp_workspace.git_operations.is_git_repository", return_value=True),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch("mcp_workspace.github_operations._client.Github") as mock_github_cls,
        ):
            manager = IssueBranchManager(mock_path)
            # Set cached github client so lazy property doesn't trigger outside patch
            manager._cached_github_client = mock_github_cls.return_value
            return manager

    def test_valid_issue_number(self, mock_manager: IssueBranchManager) -> None:
        """Test get_linked_branches with valid issue number."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL response
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "linkedBranches": {
                            "nodes": [
                                {"ref": {"name": "123-feature-branch"}},
                                {"ref": {"name": "123-hotfix"}},
                            ]
                        }
                    }
                }
            }
        }
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, mock_response)
        )

        # Test
        result = mock_manager.get_linked_branches(123)
        assert result == ["123-feature-branch", "123-hotfix"]

    def test_invalid_issue_number(self, mock_manager: IssueBranchManager) -> None:
        """Test get_linked_branches with invalid issue number."""
        # Test with negative number
        result = mock_manager.get_linked_branches(-1)
        assert result == []

        # Test with zero
        result = mock_manager.get_linked_branches(0)
        assert result == []

    def test_issue_not_found(self, mock_manager: IssueBranchManager) -> None:
        """Test get_linked_branches when issue is not found."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL response with null issue
        mock_response: dict[str, Any] = {"data": {"repository": {"issue": None}}}
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, mock_response)
        )

        # Test
        result = mock_manager.get_linked_branches(999)
        assert result == []

    def test_no_linked_branches(self, mock_manager: IssueBranchManager) -> None:
        """Test get_linked_branches when issue has no linked branches."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL response with empty nodes
        mock_response: dict[str, Any] = {
            "data": {"repository": {"issue": {"linkedBranches": {"nodes": []}}}}
        }
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, mock_response)
        )

        # Test
        result = mock_manager.get_linked_branches(123)
        assert result == []

    def test_multiple_linked_branches(self, mock_manager: IssueBranchManager) -> None:
        """Test get_linked_branches with multiple branches."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL response with multiple branches
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "linkedBranches": {
                            "nodes": [
                                {"ref": {"name": "123-feature-1"}},
                                {"ref": {"name": "123-feature-2"}},
                                {"ref": {"name": "123-feature-3"}},
                            ]
                        }
                    }
                }
            }
        }
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, mock_response)
        )

        # Test
        result = mock_manager.get_linked_branches(123)
        assert result == ["123-feature-1", "123-feature-2", "123-feature-3"]
        assert len(result) == 3

    def test_graphql_error_handling(self, mock_manager: IssueBranchManager) -> None:
        """Test get_linked_branches handles GraphQL errors gracefully."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL response with malformed data
        mock_response: dict[str, Any] = {"data": None}  # Malformed response
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, mock_response)
        )

        # Test
        result = mock_manager.get_linked_branches(123)
        assert result == []

    def test_repository_not_found(self, mock_manager: IssueBranchManager) -> None:
        """Test get_linked_branches when repository cannot be accessed."""
        # Mock _get_repository to return None
        mock_manager._repository = None
        mock_manager._get_repository = Mock(return_value=None)  # type: ignore[method-assign]

        # Test
        result = mock_manager.get_linked_branches(123)
        assert result == []

    def test_null_ref_in_nodes(self, mock_manager: IssueBranchManager) -> None:
        """Test get_linked_branches handles null ref values in nodes."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL response with null ref
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "linkedBranches": {
                            "nodes": [
                                {"ref": {"name": "123-valid-branch"}},
                                {"ref": None},  # Null ref
                                None,  # Null node
                            ]
                        }
                    }
                }
            }
        }
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, mock_response)
        )

        # Test - should skip null values and return only valid branch
        result = mock_manager.get_linked_branches(123)
        assert result == ["123-valid-branch"]


class TestGetLinkedBranchesOrNone:
    """Test suite for IssueBranchManager.get_linked_branches_or_none() method.

    Unlike get_linked_branches(), this sibling distinguishes "the issue has no
    linked branch" ([]) from "the lookup could not be completed" (None).
    """

    @pytest.fixture
    def mock_manager(self) -> IssueBranchManager:
        """Create a mock IssueBranchManager for testing."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with (
            patch("mcp_workspace.git_operations.is_git_repository", return_value=True),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch("mcp_workspace.github_operations._client.Github") as mock_github_cls,
        ):
            manager = IssueBranchManager(mock_path)
            # Set cached github client so lazy property doesn't trigger outside patch
            manager._cached_github_client = mock_github_cls.return_value
            return manager

    @staticmethod
    def _set_graphql_response(
        mock_manager: IssueBranchManager, response: dict[str, Any]
    ) -> None:
        """Point the mocked GraphQL requester at a canned response."""
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, response)
        )

    def test_success_returns_branch_names(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Successful query returns the linked branch names."""
        self._set_graphql_response(
            mock_manager,
            {
                "data": {
                    "repository": {
                        "issue": {
                            "linkedBranches": {
                                "nodes": [
                                    {"ref": {"name": "123-feature-branch"}},
                                    {"ref": {"name": "123-hotfix"}},
                                ]
                            }
                        }
                    }
                }
            },
        )

        result = mock_manager.get_linked_branches_or_none(123)
        assert result == ["123-feature-branch", "123-hotfix"]

    def test_no_linked_branches_returns_empty_list_not_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """A successful query with no linked branches is [], never None.

        This is the NOT_LINKED case; keeping it distinct from None is the whole
        point of this method.
        """
        self._set_graphql_response(
            mock_manager,
            {"data": {"repository": {"issue": {"linkedBranches": {"nodes": []}}}}},
        )

        result = mock_manager.get_linked_branches_or_none(123)
        assert result == []
        assert result is not None

    def test_invalid_issue_number_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Invalid issue numbers cannot be looked up, so they return None."""
        assert mock_manager.get_linked_branches_or_none(0) is None
        assert mock_manager.get_linked_branches_or_none(-1) is None

    def test_repository_not_found_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """An unavailable repository returns None."""
        mock_manager._repository = None
        mock_manager._get_repository = Mock(return_value=None)  # type: ignore[method-assign]

        assert mock_manager.get_linked_branches_or_none(123) is None

    def test_issue_not_found_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """A null GraphQL issue returns None rather than []."""
        self._set_graphql_response(
            mock_manager, {"data": {"repository": {"issue": None}}}
        )

        assert mock_manager.get_linked_branches_or_none(999) is None

    def test_malformed_response_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """A malformed payload returns None rather than []."""
        self._set_graphql_response(mock_manager, {"data": None})

        assert mock_manager.get_linked_branches_or_none(123) is None

    def test_graphql_server_error_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """A raised GithubException is caught and reported as None."""
        from github import GithubException

        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            side_effect=GithubException(500, {"message": "Internal Server Error"}, None)
        )

        assert mock_manager.get_linked_branches_or_none(123) is None

    def test_auth_error_returns_none_and_is_not_reraised(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Auth failures are an undeterminable lookup, not a re-raised error.

        Unlike the decorated siblings, this method does not re-raise 401/403.
        """
        from github import GithubException

        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            side_effect=GithubException(401, {"message": "Bad credentials"}, None)
        )

        assert mock_manager.get_linked_branches_or_none(123) is None
