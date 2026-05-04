"""Unit tests for IssueBranchManager."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

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
            patch(
                "mcp_workspace.github_operations.base_manager.Github"
            ) as mock_github_cls,
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


class TestCreateLinkedBranch:
    """Test suite for IssueBranchManager.create_remote_branch_for_issue() method."""

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
            patch(
                "mcp_workspace.github_operations.base_manager.Github"
            ) as mock_github_cls,
        ):
            manager = IssueBranchManager(mock_path)
            # Set cached github client so lazy property doesn't trigger outside patch
            manager._cached_github_client = mock_github_cls.return_value
            return manager

    def test_create_with_auto_name(self, mock_manager: IssueBranchManager) -> None:
        """Test creating branch with auto-generated name from issue title."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.node_id = "R_kgDOABCDEF"
        mock_repo.default_branch = "main"
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock issue
        mock_issue = Mock()
        mock_issue.node_id = "I_kwDOABCDEF123"
        mock_issue.title = "Add New Feature"
        mock_repo.get_issue = Mock(return_value=mock_issue)

        # Mock branch for getting base SHA
        mock_branch = Mock()
        mock_branch.commit.sha = "abc123def456"
        mock_repo.get_branch = Mock(return_value=mock_branch)

        # Mock get_linked_branches to return empty (no existing branches)
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Mock GraphQL mutation response (PyGithub unwraps the 'data' wrapper)
        mock_response = {
            "createLinkedBranch": {
                "linkedBranch": {
                    "id": "LB_kwDOABCDEF",
                    "ref": {
                        "name": "123-add-new-feature",
                        "target": {"oid": "abc123def456"},
                    },
                }
            }
        }
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_named_mutation = Mock(  # type: ignore[attr-defined]
            return_value=({}, mock_response)
        )

        # Test
        result = mock_manager.create_remote_branch_for_issue(123)

        # Verify result
        assert result["success"] is True
        assert result["branch_name"] == "123-add-new-feature"
        assert result["error"] is None
        assert result["existing_branches"] == []

        # Verify issue was fetched
        mock_repo.get_issue.assert_called_once_with(123)

        # Verify GraphQL mutation was called
        mock_manager._github_client._Github__requester.graphql_named_mutation.assert_called_once()  # type: ignore[attr-defined]

    def test_create_with_custom_name(self, mock_manager: IssueBranchManager) -> None:
        """Test creating branch with custom branch name."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.node_id = "R_kgDOABCDEF"
        mock_repo.default_branch = "main"
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock issue
        mock_issue = Mock()
        mock_issue.node_id = "I_kwDOABCDEF123"
        mock_issue.title = "Add New Feature"
        mock_repo.get_issue = Mock(return_value=mock_issue)

        # Mock branch for getting base SHA
        mock_branch = Mock()
        mock_branch.commit.sha = "abc123def456"
        mock_repo.get_branch = Mock(return_value=mock_branch)

        # Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Mock GraphQL mutation response (PyGithub unwraps the 'data' wrapper)
        mock_response = {
            "createLinkedBranch": {
                "linkedBranch": {
                    "id": "LB_kwDOABCDEF",
                    "ref": {
                        "name": "custom-branch-name",
                        "target": {"oid": "abc123def456"},
                    },
                }
            }
        }
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_named_mutation = Mock(  # type: ignore[attr-defined]
            return_value=({}, mock_response)
        )

        # Test with custom branch name
        result = mock_manager.create_remote_branch_for_issue(
            123, branch_name="custom-branch-name"
        )

        # Verify result
        assert result["success"] is True
        assert result["branch_name"] == "custom-branch-name"
        assert result["error"] is None
        assert result["existing_branches"] == []

    def test_create_with_base_branch(self, mock_manager: IssueBranchManager) -> None:
        """Test creating branch with custom base branch."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.node_id = "R_kgDOABCDEF"
        mock_repo.default_branch = "main"
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock issue
        mock_issue = Mock()
        mock_issue.node_id = "I_kwDOABCDEF123"
        mock_issue.title = "Add New Feature"
        mock_repo.get_issue = Mock(return_value=mock_issue)

        # Mock branch for getting base SHA (custom develop branch)
        mock_branch = Mock()
        mock_branch.commit.sha = "xyz789abc123"
        mock_repo.get_branch = Mock(return_value=mock_branch)

        # Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Mock GraphQL mutation response (PyGithub unwraps the 'data' wrapper)
        mock_response = {
            "createLinkedBranch": {
                "linkedBranch": {
                    "id": "LB_kwDOABCDEF",
                    "ref": {
                        "name": "123-add-new-feature",
                        "target": {"oid": "xyz789abc123"},
                    },
                }
            }
        }
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_named_mutation = Mock(  # type: ignore[attr-defined]
            return_value=({}, mock_response)
        )

        # Test with custom base branch
        result = mock_manager.create_remote_branch_for_issue(123, base_branch="develop")

        # Verify result
        assert result["success"] is True
        assert result["branch_name"] == "123-add-new-feature"
        assert result["error"] is None

        # Verify base branch was used
        mock_repo.get_branch.assert_called_once_with("develop")

    def test_duplicate_prevention_default(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Test that duplicate branch creation is prevented by default (allow_multiple=False)."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock get_linked_branches to return existing branches
        mock_manager.get_linked_branches = Mock(  # type: ignore[method-assign]
            return_value=["123-feature-branch", "123-hotfix"]
        )

        # Test - should fail due to existing branches
        result = mock_manager.create_remote_branch_for_issue(123)

        # Verify result
        assert result["success"] is False
        assert result["branch_name"] == ""
        assert result["error"] is not None
        assert "linked branches" in result["error"].lower()
        assert result["existing_branches"] == ["123-feature-branch", "123-hotfix"]

        # Verify get_linked_branches was called
        mock_manager.get_linked_branches.assert_called_once_with(123)

    def test_allow_multiple_branches(self, mock_manager: IssueBranchManager) -> None:
        """Test that multiple branches can be created when allow_multiple=True."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.node_id = "R_kgDOABCDEF"
        mock_repo.default_branch = "main"
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock issue
        mock_issue = Mock()
        mock_issue.node_id = "I_kwDOABCDEF123"
        mock_issue.title = "Add New Feature"
        mock_repo.get_issue = Mock(return_value=mock_issue)

        # Mock branch for getting base SHA
        mock_branch = Mock()
        mock_branch.commit.sha = "abc123def456"
        mock_repo.get_branch = Mock(return_value=mock_branch)

        # Mock get_linked_branches to return existing branch
        mock_manager.get_linked_branches = Mock(return_value=["123-existing-branch"])  # type: ignore[method-assign]

        # Mock GraphQL mutation response (PyGithub unwraps the 'data' wrapper)
        mock_response = {
            "createLinkedBranch": {
                "linkedBranch": {
                    "id": "LB_kwDOABCDEF",
                    "ref": {
                        "name": "123-second-branch",
                        "target": {"oid": "abc123def456"},
                    },
                }
            }
        }
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_named_mutation = Mock(  # type: ignore[attr-defined]
            return_value=({}, mock_response)
        )

        # Test with allow_multiple=True
        result = mock_manager.create_remote_branch_for_issue(
            123, branch_name="123-second-branch", allow_multiple=True
        )

        # Verify result - should succeed despite existing branch
        assert result["success"] is True
        assert result["branch_name"] == "123-second-branch"
        assert result["error"] is None

        # Verify get_linked_branches was NOT called (skipped when allow_multiple=True)
        mock_manager.get_linked_branches.assert_not_called()

    def test_invalid_issue_number(self, mock_manager: IssueBranchManager) -> None:
        """Test creating branch with invalid issue number."""
        # Test with negative number
        result = mock_manager.create_remote_branch_for_issue(-1)
        assert result["success"] is False
        assert result["error"] is not None

        # Test with zero
        result = mock_manager.create_remote_branch_for_issue(0)
        assert result["success"] is False
        assert result["error"] is not None

    def test_issue_not_found(self, mock_manager: IssueBranchManager) -> None:
        """Test creating branch when issue is not found."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Mock get_issue to raise exception
        from github import GithubException

        mock_repo.get_issue = Mock(
            side_effect=GithubException(404, {"message": "Not Found"}, None)
        )

        # Test
        result = mock_manager.create_remote_branch_for_issue(999)

        # Verify result - should return default error result due to decorator
        assert result["success"] is False

    def test_permission_error(self, mock_manager: IssueBranchManager) -> None:
        """Test creating branch when user lacks permissions.

        Permission errors (403) are re-raised by the decorator to allow
        calling code to handle authentication issues appropriately.
        """
        # Mock repository
        mock_repo = Mock()
        mock_repo.node_id = "R_kgDOABCDEF"
        mock_repo.default_branch = "main"
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock issue
        mock_issue = Mock()
        mock_issue.node_id = "I_kwDOABCDEF123"
        mock_issue.title = "Add New Feature"
        mock_repo.get_issue = Mock(return_value=mock_issue)

        # Mock branch for getting base SHA
        mock_branch = Mock()
        mock_branch.commit.sha = "abc123def456"
        mock_repo.get_branch = Mock(return_value=mock_branch)

        # Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Mock GraphQL mutation to raise permission error
        from github import GithubException

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_named_mutation = Mock(  # type: ignore[attr-defined]
            side_effect=GithubException(403, {"message": "Forbidden"}, None)
        )

        # Test - should re-raise the GithubException
        with pytest.raises(GithubException) as exc_info:
            mock_manager.create_remote_branch_for_issue(123)

        # Verify it's a 403 error
        assert exc_info.value.status == 403

    def test_base_branch_not_found(self, mock_manager: IssueBranchManager) -> None:
        """Test creating branch when specified base branch doesn't exist."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.node_id = "R_kgDOABCDEF"
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock issue
        mock_issue = Mock()
        mock_issue.node_id = "I_kwDOABCDEF123"
        mock_issue.title = "Add New Feature"
        mock_repo.get_issue = Mock(return_value=mock_issue)

        # Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Mock get_branch to raise exception for non-existent branch
        from github import GithubException

        mock_repo.get_branch = Mock(
            side_effect=GithubException(404, {"message": "Branch not found"}, None)
        )

        # Test
        result = mock_manager.create_remote_branch_for_issue(
            123, base_branch="nonexistent"
        )

        # Verify result - should return default error result due to decorator
        assert result["success"] is False

    def test_repository_not_found(self, mock_manager: IssueBranchManager) -> None:
        """Test creating branch when repository cannot be accessed."""
        # Mock _get_repository to return None
        mock_manager._repository = None
        mock_manager._get_repository = Mock(return_value=None)  # type: ignore[method-assign]

        # Test
        result = mock_manager.create_remote_branch_for_issue(123)

        # Verify result
        assert result["success"] is False
        assert result["error"] is not None

    def test_graphql_mutation_malformed_response(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Test handling of malformed GraphQL mutation response."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.node_id = "R_kgDOABCDEF"
        mock_repo.default_branch = "main"
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock issue
        mock_issue = Mock()
        mock_issue.node_id = "I_kwDOABCDEF123"
        mock_issue.title = "Add New Feature"
        mock_repo.get_issue = Mock(return_value=mock_issue)

        # Mock branch for getting base SHA
        mock_branch = Mock()
        mock_branch.commit.sha = "abc123def456"
        mock_repo.get_branch = Mock(return_value=mock_branch)

        # Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Mock GraphQL mutation response with malformed data
        mock_response = {"data": None}  # Malformed response
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_named_mutation = Mock(  # type: ignore[attr-defined]
            return_value=({}, mock_response)
        )

        # Test
        result = mock_manager.create_remote_branch_for_issue(123)

        # Verify result - should fail gracefully
        assert result["success"] is False
        assert result["error"] is not None

    def test_graphql_response_format_correct_parsing(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Test that PyGithub's response format (without 'data' wrapper) is parsed correctly.

        This test verifies the fix for issue #110 where the code incorrectly expected
        the response to be wrapped in a 'data' key, but PyGithub's graphql_named_mutation
        already unwraps it.
        """
        # Mock repository
        mock_repo = Mock()
        mock_repo.node_id = "R_kgDOPpBE2w"
        mock_repo.default_branch = "main"
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock issue
        mock_issue = Mock()
        mock_issue.node_id = "I_kwDOPpBE287Px0Dx"
        mock_issue.title = "Validate and Reset GitHub Issue Labels"
        mock_repo.get_issue = Mock(return_value=mock_issue)

        # Mock branch for getting base SHA
        mock_branch = Mock()
        mock_branch.commit.sha = "28e6978c9bf83797ea4a0825ed042a76e2fc2636"
        mock_repo.get_branch = Mock(return_value=mock_branch)

        # Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Mock GraphQL mutation response - EXACTLY as PyGithub returns it (without 'data' wrapper)
        # This is the actual format from the logs in issue #110
        mock_response = {
            "createLinkedBranch": {
                "linkedBranch": {
                    "id": "LB_kwDOz8dA8c4ApN7w",
                    "ref": {
                        "name": "110-validate-and-reset-github-issue-labels",
                        "target": {"oid": "28e6978c9bf83797ea4a0825ed042a76e2fc2636"},
                    },
                }
            }
        }
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_named_mutation = Mock(  # type: ignore[attr-defined]
            return_value=({}, mock_response)
        )

        # Test - this should now succeed with the fix
        result = mock_manager.create_remote_branch_for_issue(110)

        # Verify result - should succeed
        assert result["success"] is True
        assert result["branch_name"] == "110-validate-and-reset-github-issue-labels"
        assert result["error"] is None
        assert result["existing_branches"] == []

    def _setup_create_branch_mocks(self, mock_manager: IssueBranchManager) -> Mock:
        mock_repo = Mock()
        mock_repo.node_id = "R_kgDOABCDEF"
        mock_repo.default_branch = "main"
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_issue = Mock()
        mock_issue.node_id = "I_kwDOABCDEF123"
        mock_issue.title = "Add New Feature"
        mock_repo.get_issue = Mock(return_value=mock_issue)

        mock_branch = Mock()
        mock_branch.commit.sha = "abc123def456"
        mock_repo.get_branch = Mock(return_value=mock_branch)

        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        return mock_manager._github_client._Github__requester  # type: ignore[attr-defined,no-any-return]

    def test_retries_on_missing_ref_then_succeeds(
        self, mock_manager: IssueBranchManager
    ) -> None:
        requester = self._setup_create_branch_mocks(mock_manager)

        flake_response = {"linkedBranch": None}
        success_response = {
            "linkedBranch": {
                "id": "LB_kwDOABCDEF",
                "ref": {
                    "name": "123-add-new-feature",
                    "target": {"oid": "abc123def456"},
                },
            }
        }
        requester.graphql_named_mutation = Mock(
            side_effect=[
                ({}, flake_response),
                ({}, success_response),
            ]
        )

        with patch(
            "mcp_workspace.github_operations.issues.branch_manager.time.sleep"
        ) as mock_sleep:
            result = mock_manager.create_remote_branch_for_issue(123)

        assert result["success"] is True
        assert result["branch_name"] == "123-add-new-feature"
        assert requester.graphql_named_mutation.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    def test_exhausts_retries_when_ref_always_missing(
        self, mock_manager: IssueBranchManager
    ) -> None:
        requester = self._setup_create_branch_mocks(mock_manager)

        flake_response = {"linkedBranch": None}
        requester.graphql_named_mutation = Mock(return_value=({}, flake_response))

        with patch(
            "mcp_workspace.github_operations.issues.branch_manager.time.sleep"
        ) as mock_sleep:
            result = mock_manager.create_remote_branch_for_issue(123)

        assert result["success"] is False
        assert result["error"] is not None
        assert "Missing branch reference" in result["error"]
        assert requester.graphql_named_mutation.call_count == 3
        # Two retries → two sleeps with exponential backoff: 1s, 2s
        assert mock_sleep.call_args_list == [((1.0,),), ((2.0,),)]

    def test_no_retry_on_non_transient_error(
        self, mock_manager: IssueBranchManager
    ) -> None:
        requester = self._setup_create_branch_mocks(mock_manager)

        # `errors` field is a permanent failure — must not retry
        permanent_error_response = {"errors": [{"message": "Branch already exists"}]}
        requester.graphql_named_mutation = Mock(
            return_value=({}, permanent_error_response)
        )

        with patch(
            "mcp_workspace.github_operations.issues.branch_manager.time.sleep"
        ) as mock_sleep:
            result = mock_manager.create_remote_branch_for_issue(123)

        assert result["success"] is False
        assert requester.graphql_named_mutation.call_count == 1
        mock_sleep.assert_not_called()


class TestDeleteLinkedBranch:
    """Test suite for IssueBranchManager.delete_linked_branch() method."""

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
            patch(
                "mcp_workspace.github_operations.base_manager.Github"
            ) as mock_github_cls,
        ):
            manager = IssueBranchManager(mock_path)
            # Set cached github client so lazy property doesn't trigger outside patch
            manager._cached_github_client = mock_github_cls.return_value
            return manager

    def test_successful_unlink(self, mock_manager: IssueBranchManager) -> None:
        """Test successfully unlinking a branch from an issue."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL query response with linked branches including IDs
        query_response: dict[str, Any] = {
            "data": {
                "repository": {
                    "issue": {
                        "linkedBranches": {
                            "nodes": [
                                {
                                    "id": "LB_kwDOABCDEF123",
                                    "ref": {"name": "123-feature-branch"},
                                },
                                {
                                    "id": "LB_kwDOABCDEF456",
                                    "ref": {"name": "123-hotfix"},
                                },
                            ]
                        }
                    }
                }
            }
        }

        # Mock GraphQL mutation response
        mutation_response = {"data": {"deleteLinkedBranch": {"clientMutationId": None}}}

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, query_response)
        )
        mock_manager._github_client._Github__requester.graphql_named_mutation = Mock(  # type: ignore[attr-defined]
            return_value=({}, mutation_response)
        )

        # Test - delete the first branch
        result = mock_manager.delete_linked_branch(123, "123-feature-branch")

        # Verify result
        assert result is True

        # Verify GraphQL query was called
        mock_manager._github_client._Github__requester.graphql_query.assert_called_once()  # type: ignore[attr-defined]

        # Verify GraphQL mutation was called with correct linkedBranchId
        mock_manager._github_client._Github__requester.graphql_named_mutation.assert_called_once()  # type: ignore[attr-defined]
        call_args = (
            mock_manager._github_client._Github__requester.graphql_named_mutation.call_args  # type: ignore[attr-defined]
        )
        assert call_args[1]["mutation_input"]["linkedBranchId"] == "LB_kwDOABCDEF123"

    def test_branch_not_linked(self, mock_manager: IssueBranchManager) -> None:
        """Test attempting to unlink a branch that is not linked to the issue."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL query response with different linked branches
        query_response: dict[str, Any] = {
            "data": {
                "repository": {
                    "issue": {
                        "linkedBranches": {
                            "nodes": [
                                {
                                    "id": "LB_kwDOABCDEF123",
                                    "ref": {"name": "123-feature-branch"},
                                },
                                {
                                    "id": "LB_kwDOABCDEF456",
                                    "ref": {"name": "123-hotfix"},
                                },
                            ]
                        }
                    }
                }
            }
        }

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, query_response)
        )

        # Test - try to delete a branch that doesn't exist
        result = mock_manager.delete_linked_branch(123, "123-nonexistent-branch")

        # Verify result - should return False
        assert result is False

        # Verify GraphQL query was called
        mock_manager._github_client._Github__requester.graphql_query.assert_called_once()  # type: ignore[attr-defined]

        # Verify mutation was NOT called (branch not found)
        assert (
            not hasattr(
                mock_manager._github_client._Github__requester, "graphql_named_mutation"  # type: ignore[attr-defined]
            )
            or not mock_manager._github_client._Github__requester.graphql_named_mutation.called  # type: ignore[attr-defined]
        )

    def test_invalid_issue_number(self, mock_manager: IssueBranchManager) -> None:
        """Test delete_linked_branch with invalid issue numbers."""
        # Test with negative number
        result = mock_manager.delete_linked_branch(-1, "branch-name")
        assert result is False

        # Test with zero
        result = mock_manager.delete_linked_branch(0, "branch-name")
        assert result is False

    def test_empty_branch_name(self, mock_manager: IssueBranchManager) -> None:
        """Test delete_linked_branch with empty or whitespace branch name."""
        # Test with empty string
        result = mock_manager.delete_linked_branch(123, "")
        assert result is False

        # Test with whitespace only
        result = mock_manager.delete_linked_branch(123, "   ")
        assert result is False

        # Test with None (if type checking allows)
        result = mock_manager.delete_linked_branch(123, "")
        assert result is False

    def test_issue_not_found(self, mock_manager: IssueBranchManager) -> None:
        """Test delete_linked_branch when issue is not found."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL query response with null issue
        query_response: dict[str, Any] = {"data": {"repository": {"issue": None}}}

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, query_response)
        )

        # Test
        result = mock_manager.delete_linked_branch(999, "123-feature-branch")

        # Verify result - should return False
        assert result is False

        # Verify GraphQL query was called
        mock_manager._github_client._Github__requester.graphql_query.assert_called_once()  # type: ignore[attr-defined]

    def test_no_linked_branches(self, mock_manager: IssueBranchManager) -> None:
        """Test delete_linked_branch when issue has no linked branches."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL query response with empty nodes
        query_response: dict[str, Any] = {
            "data": {"repository": {"issue": {"linkedBranches": {"nodes": []}}}}
        }

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, query_response)
        )

        # Test
        result = mock_manager.delete_linked_branch(123, "123-feature-branch")

        # Verify result - should return False (branch not found)
        assert result is False

    def test_repository_not_found(self, mock_manager: IssueBranchManager) -> None:
        """Test delete_linked_branch when repository cannot be accessed."""
        # Mock _get_repository to return None
        mock_manager._repository = None
        mock_manager._get_repository = Mock(return_value=None)  # type: ignore[method-assign]

        # Test
        result = mock_manager.delete_linked_branch(123, "123-feature-branch")

        # Verify result
        assert result is False

    def test_graphql_query_error(self, mock_manager: IssueBranchManager) -> None:
        """Test delete_linked_branch handles GraphQL query errors gracefully."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL query to raise exception
        from github import GithubException

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            side_effect=GithubException(500, {"message": "Internal Server Error"}, None)
        )

        # Test
        result = mock_manager.delete_linked_branch(123, "123-feature-branch")

        # Verify result - should return False due to decorator
        assert result is False

    def test_graphql_mutation_error(self, mock_manager: IssueBranchManager) -> None:
        """Test delete_linked_branch handles GraphQL mutation errors.

        Permission errors (403) are re-raised by the decorator to allow
        calling code to handle authentication issues appropriately.
        """
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL query response with linked branch
        query_response: dict[str, Any] = {
            "data": {
                "repository": {
                    "issue": {
                        "linkedBranches": {
                            "nodes": [
                                {
                                    "id": "LB_kwDOABCDEF123",
                                    "ref": {"name": "123-feature-branch"},
                                }
                            ]
                        }
                    }
                }
            }
        }

        # Mock GraphQL mutation to raise exception
        from github import GithubException

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, query_response)
        )
        mock_manager._github_client._Github__requester.graphql_named_mutation = Mock(  # type: ignore[attr-defined]
            side_effect=GithubException(403, {"message": "Forbidden"}, None)
        )

        # Test - should re-raise the GithubException
        with pytest.raises(GithubException) as exc_info:
            mock_manager.delete_linked_branch(123, "123-feature-branch")

        # Verify it's a 403 error
        assert exc_info.value.status == 403

    def test_malformed_query_response(self, mock_manager: IssueBranchManager) -> None:
        """Test delete_linked_branch handles malformed GraphQL query response."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL query response with malformed data
        query_response: dict[str, Any] = {"data": None}

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, query_response)
        )

        # Test
        result = mock_manager.delete_linked_branch(123, "123-feature-branch")

        # Verify result - should return False
        assert result is False

    def test_null_ref_in_nodes(self, mock_manager: IssueBranchManager) -> None:
        """Test delete_linked_branch handles null ref values in nodes."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL query response with null ref and valid branch
        query_response: dict[str, Any] = {
            "data": {
                "repository": {
                    "issue": {
                        "linkedBranches": {
                            "nodes": [
                                {"ref": None},  # Null ref
                                None,  # Null node
                                {
                                    "id": "LB_kwDOABCDEF123",
                                    "ref": {"name": "123-valid-branch"},
                                },
                            ]
                        }
                    }
                }
            }
        }

        # Mock GraphQL mutation response
        mutation_response = {"data": {"deleteLinkedBranch": {"clientMutationId": None}}}

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, query_response)
        )
        mock_manager._github_client._Github__requester.graphql_named_mutation = Mock(  # type: ignore[attr-defined]
            return_value=({}, mutation_response)
        )

        # Test - delete the valid branch (should skip null values)
        result = mock_manager.delete_linked_branch(123, "123-valid-branch")

        # Verify result
        assert result is True

    def test_case_sensitive_branch_matching(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Test that branch name matching is case-sensitive."""
        # Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Mock GraphQL query response with lowercase branch name
        query_response: dict[str, Any] = {
            "data": {
                "repository": {
                    "issue": {
                        "linkedBranches": {
                            "nodes": [
                                {
                                    "id": "LB_kwDOABCDEF123",
                                    "ref": {"name": "123-feature-branch"},
                                }
                            ]
                        }
                    }
                }
            }
        }

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, query_response)
        )

        # Test - try to delete with uppercase (should not match)
        result = mock_manager.delete_linked_branch(123, "123-FEATURE-BRANCH")

        # Verify result - should return False (case mismatch)
        assert result is False
