"""Unit tests for IssueBranchManager.create_remote_branch_for_issue() method."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from mcp_workspace.github_operations.issues import (
    IssueBranchManager,
)


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
            patch("mcp_workspace.github_operations._client.Github") as mock_github_cls,
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
