"""Unit tests for IssueBranchManager.get_branch_with_pr_fallback() method."""

# pylint: disable=protected-access  # Tests need to access protected members for mocking

from typing import Any
from unittest.mock import Mock

from github import GithubException

from mcp_workspace.github_operations.issues import IssueBranchManager


class TestGetBranchWithPRFallback:
    """Test suite for IssueBranchManager.get_branch_with_pr_fallback()."""

    def test_multiple_linked_branches_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Two linked branches returns None (ambiguous)."""
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_manager.get_linked_branches = Mock(  # type: ignore[method-assign]
            return_value=["123-branch-a", "123-branch-b"]
        )

        # GraphQL should NOT be called (short-circuit)
        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_graphql_query = Mock()
        mock_manager._github_client._Github__requester.graphql_query = mock_graphql_query  # type: ignore[attr-defined]

        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        assert result is None
        mock_graphql_query.assert_not_called()

    def test_closed_pr_with_existing_branch(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Closed PR with existing branch returns branch name."""
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        timeline_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": 50,
                                        "state": "CLOSED",
                                        "isDraft": False,
                                        "headRefName": "123-closed-branch",
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

        # Branch exists
        mock_repo.get_branch = Mock(return_value=Mock())

        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        assert result == "123-closed-branch"
        mock_repo.get_branch.assert_called_once_with("123-closed-branch")

    def test_closed_pr_with_deleted_branch(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Closed PR with deleted branch falls through to pattern search."""
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        timeline_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": 50,
                                        "state": "CLOSED",
                                        "isDraft": False,
                                        "headRefName": "123-deleted-branch",
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

        # Branch deleted — get_branch raises GithubException
        mock_repo.get_branch = Mock(
            side_effect=GithubException(404, {"message": "Branch not found"}, None)
        )

        # Pattern search also returns None
        mock_manager._search_branches_by_pattern = Mock(return_value=None)  # type: ignore[method-assign]

        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        assert result is None
        mock_repo.get_branch.assert_called_once_with("123-deleted-branch")
        mock_manager._search_branches_by_pattern.assert_called_once_with(123, mock_repo)

    def test_merged_pr_not_matched(self, mock_manager: IssueBranchManager) -> None:
        """Merged PR in timeline is skipped (state is MERGED, not CLOSED)."""
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        timeline_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": 50,
                                        "state": "MERGED",
                                        "isDraft": False,
                                        "headRefName": "123-merged-branch",
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

        # get_branch should NOT be called (MERGED is not CLOSED)
        mock_repo.get_branch = Mock()
        mock_manager._search_branches_by_pattern = Mock(return_value=None)  # type: ignore[method-assign]

        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        assert result is None
        mock_repo.get_branch.assert_not_called()

    def test_closed_pr_25_check_cap(self, mock_manager: IssueBranchManager) -> None:
        """30 closed PRs, all branches deleted — stops checking after 25."""
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        # Build 30 closed PRs
        nodes = [
            {
                "__typename": "CrossReferencedEvent",
                "source": {
                    "number": i,
                    "state": "CLOSED",
                    "isDraft": False,
                    "headRefName": f"123-branch-{i}",
                },
            }
            for i in range(30)
        ]

        timeline_response = {
            "data": {"repository": {"issue": {"timelineItems": {"nodes": nodes}}}}
        }

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, timeline_response)
        )

        # All branches deleted
        mock_repo.get_branch = Mock(
            side_effect=GithubException(404, {"message": "Not found"}, None)
        )

        mock_manager._search_branches_by_pattern = Mock(return_value=None)  # type: ignore[method-assign]

        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        assert result is None
        # Should only check 25 branches, not all 30
        assert mock_repo.get_branch.call_count == 25

    def test_closed_pr_most_recent_preferred(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Multiple closed PRs with existing branches — returns highest PR number."""
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        timeline_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": 10,
                                        "state": "CLOSED",
                                        "isDraft": False,
                                        "headRefName": "123-old-branch",
                                    },
                                },
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": 55,
                                        "state": "CLOSED",
                                        "isDraft": False,
                                        "headRefName": "123-newest-branch",
                                    },
                                },
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": 30,
                                        "state": "CLOSED",
                                        "isDraft": False,
                                        "headRefName": "123-middle-branch",
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

        # All branches exist
        mock_repo.get_branch = Mock(return_value=Mock())

        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        # Should return the branch from the highest PR number (55)
        assert result == "123-newest-branch"
        mock_repo.get_branch.assert_called_once_with("123-newest-branch")

    def test_closed_pr_prefers_open_pr(self, mock_manager: IssueBranchManager) -> None:
        """Both open and closed PRs exist — returns open PR branch (step order)."""
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        timeline_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": 50,
                                        "state": "CLOSED",
                                        "isDraft": False,
                                        "headRefName": "123-closed-branch",
                                    },
                                },
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "source": {
                                        "number": 60,
                                        "state": "OPEN",
                                        "isDraft": False,
                                        "headRefName": "123-open-branch",
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

        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        # Open PR is checked first (step 6), before closed PR fallback (step 7)
        assert result == "123-open-branch"

    def test_pattern_fallback_used_when_no_prs(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """No linked branches, no PRs — pattern search is called and returns result."""
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]

        timeline_response: dict[str, Any] = {
            "data": {"repository": {"issue": {"timelineItems": {"nodes": []}}}}
        }

        mock_manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, timeline_response)
        )

        # Pattern search finds a branch
        mock_manager._search_branches_by_pattern = Mock(  # type: ignore[method-assign]
            return_value="123-pattern-match"
        )

        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        assert result == "123-pattern-match"
        mock_manager._search_branches_by_pattern.assert_called_once_with(123, mock_repo)

    def test_pattern_fallback_not_called_when_linked_branch_found(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Linked branch exists — pattern search NOT called."""
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        mock_manager._repository = mock_repo

        mock_manager.get_linked_branches = Mock(  # type: ignore[method-assign]
            return_value=["123-linked"]
        )

        mock_manager._search_branches_by_pattern = Mock()  # type: ignore[method-assign]

        result = mock_manager.get_branch_with_pr_fallback(
            issue_number=123, repo_owner="test-owner", repo_name="test-repo"
        )

        assert result == "123-linked"
        mock_manager._search_branches_by_pattern.assert_not_called()
