"""Unit tests for IssueBranchManager.get_branch_with_pr_fallback() method."""

# pylint: disable=protected-access  # Tests need to access protected members for mocking

from typing import Any
from unittest.mock import Mock

import pytest
from github import GithubException

from mcp_workspace.github_operations.issues import IssueBranchManager


class TestGetBranchWithPRFallback:
    """Test suite for IssueBranchManager.get_branch_with_pr_fallback()."""

    def test_linked_branch_found_returns_branch_name(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Test branch found via linkedBranches (primary path).

        When linkedBranches returns a branch, should return immediately
        without querying PR timeline.
        """
        # Setup: Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Setup: Mock get_linked_branches to return branch
        mock_manager.get_linked_branches = Mock(  # type: ignore[method-assign]
            return_value=["123-feature-branch"]
        )

        # Setup: Mock GraphQL client (should NOT be called)
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_graphql_query = Mock()
        mock_manager._github_client._Github__requester.graphql_query = mock_graphql_query  # type: ignore[attr-defined]

        # Execute
        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        # Verify
        assert result == "123-feature-branch"
        mock_manager.get_linked_branches.assert_called_once_with(123)
        # GraphQL should NOT be called (short-circuit)
        mock_graphql_query.assert_not_called()

    @pytest.mark.parametrize(
        "pr_state,is_draft,pr_number",
        [
            ("OPEN", True, 42),  # Draft PR
            ("OPEN", False, 43),  # Open (non-draft) PR
        ],
    )
    def test_no_linked_branch_single_pr_returns_branch(
        self,
        mock_manager: IssueBranchManager,
        pr_state: str,
        is_draft: bool,
        pr_number: int,
    ) -> None:
        """Test fallback: no linkedBranches, single draft/open PR found."""
        # Setup: Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Setup: Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Setup: Mock GraphQL timeline response with single PR
        timeline_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": pr_number,
                                        "state": pr_state,
                                        "isDraft": is_draft,
                                        "headRefName": "123-feature-branch",
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        }

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, timeline_response)
        )

        # Execute
        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        # Verify
        assert result == "123-feature-branch"
        mock_manager.get_linked_branches.assert_called_once_with(123)
        mock_manager._github_client._Github__requester.graphql_query.assert_called_once()  # type: ignore[attr-defined]

    def test_no_linked_branch_multiple_prs_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Test multiple PRs found returns None with warning."""
        # Setup: Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Setup: Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Setup: Mock GraphQL timeline response with TWO PRs
        timeline_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": 42,
                                        "state": "OPEN",
                                        "isDraft": True,
                                        "headRefName": "123-feature-branch-1",
                                    },
                                },
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": 43,
                                        "state": "OPEN",
                                        "isDraft": False,
                                        "headRefName": "123-feature-branch-2",
                                    },
                                },
                            ]
                        }
                    }
                }
            }
        }

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, timeline_response)
        )

        # Execute
        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        # Verify
        assert result is None
        mock_manager.get_linked_branches.assert_called_once_with(123)
        mock_manager._github_client._Github__requester.graphql_query.assert_called_once()  # type: ignore[attr-defined]

    def test_no_linked_branch_no_prs_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Test no linkedBranches and no PRs falls through to pattern search."""
        # Setup: Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Setup: Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Setup: Mock GraphQL timeline response with empty nodes
        timeline_response: dict[str, Any] = {
            "data": {"repository": {"issue": {"timelineItems": {"nodes": []}}}}
        }

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, timeline_response)
        )

        # Setup: Mock pattern search to return None
        mock_manager._search_branches_by_pattern = Mock(return_value=None)  # type: ignore[method-assign]

        # Execute
        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        # Verify
        assert result is None
        mock_manager.get_linked_branches.assert_called_once_with(123)
        mock_manager._github_client._Github__requester.graphql_query.assert_called_once()  # type: ignore[attr-defined]
        mock_manager._search_branches_by_pattern.assert_called_once_with(123, mock_repo)

    def test_invalid_issue_number_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Test invalid issue numbers return None."""
        # Test with negative number
        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=-1, repo_owner="test-owner", repo_name="test-repo"
        )
        assert result is None

        # Test with zero
        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=0, repo_owner="test-owner", repo_name="test-repo"
        )
        assert result is None

    def test_graphql_error_returns_none(self, mock_manager: IssueBranchManager) -> None:
        """Test GraphQL errors handled by decorator return None."""
        # Setup: Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Setup: Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Setup: Mock GraphQL to raise exception
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            side_effect=GithubException(500, {"message": "Internal Server Error"}, None)
        )

        # Execute
        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        # Verify
        assert result is None

    def test_repository_not_found_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Test repository access failure returns None."""
        # Mock _get_repository to return None
        mock_manager._repository = None
        mock_manager._get_repository = Mock(return_value=None)  # type: ignore[method-assign]

        # Execute
        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        # Verify
        assert result is None

    def test_malformed_timeline_response_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Test malformed GraphQL timeline response returns None."""
        # Setup: Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Setup: Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Setup: Mock GraphQL response with malformed data
        malformed_response: dict[str, Any] = {"data": None}  # Malformed response

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, malformed_response)
        )

        # Execute
        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        # Verify
        assert result is None

    def test_issue_not_found_in_timeline_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Test timeline query when issue is not found returns None."""
        # Setup: Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Setup: Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Setup: Mock GraphQL response with null issue
        timeline_response: dict[str, Any] = {"data": {"repository": {"issue": None}}}

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, timeline_response)
        )

        # Execute
        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=999, repo_owner="test-owner", repo_name="test-repo"
        )

        # Verify
        assert result is None

    def test_closed_prs_filtered_out(self, mock_manager: IssueBranchManager) -> None:
        """Test that closed PRs are filtered out and only OPEN PRs are considered."""
        # Setup: Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Setup: Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Setup: Mock GraphQL timeline response with closed and open PRs
        timeline_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": 40,
                                        "state": "CLOSED",
                                        "isDraft": False,
                                        "headRefName": "123-closed-pr",
                                    },
                                },
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": 42,
                                        "state": "OPEN",
                                        "isDraft": True,
                                        "headRefName": "123-feature-branch",
                                    },
                                },
                            ]
                        }
                    }
                }
            }
        }

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, timeline_response)
        )

        # Execute
        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        # Verify - should return the OPEN PR branch, ignoring CLOSED
        assert result == "123-feature-branch"

    def test_non_pr_cross_references_filtered_out(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Test that non-PR cross-references are filtered out."""
        # Setup: Mock repository
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        # Setup: Mock get_linked_branches to return empty
        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Setup: Mock GraphQL timeline response with non-PR cross-reference
        timeline_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        # This is an Issue, not a PR - missing PR-specific fields
                                        "number": 40,
                                        "title": "Related issue",
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        }

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, timeline_response)
        )

        # Setup: Mock pattern search to return None
        mock_manager._search_branches_by_pattern = Mock(return_value=None)  # type: ignore[method-assign]

        # Execute
        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        # Verify - should return None as no valid PRs found
        assert result is None
