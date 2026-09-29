"""Unit tests for IssueManager sub-issue operations with mocked dependencies."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.issues import IssueManager
from mcp_workspace.github_operations.issues.sub_issues_mixin import sub_issue_total

from .._issue_test_helpers import make_mock_issue


def _make_issue(number: int) -> MagicMock:
    """Create a mock issue that passes the pull-request guard."""
    mock_issue = make_mock_issue(number)
    mock_issue.pull_request = None
    return mock_issue


@pytest.mark.git_integration
class TestIssueManagerSubIssues:
    """Unit tests for IssueManager sub-issue operations with mocked dependencies."""

    def test_add_sub_issue_success(self, mock_issue_manager: IssueManager) -> None:
        """The child object is linked and the refetched parent is returned."""
        mock_parent = _make_issue(3)
        mock_child = _make_issue(5)
        mock_refetched_parent = _make_issue(3)
        mock_refetched_parent.sub_issues_summary.total = 1
        mock_issue_manager._repository.get_issue.side_effect = [
            mock_parent,
            mock_child,
            mock_refetched_parent,
        ]

        result = mock_issue_manager.add_sub_issue(3, 5)

        mock_parent.add_sub_issue.assert_called_once_with(mock_child)
        assert result is mock_refetched_parent

    def test_remove_sub_issue_success(self, mock_issue_manager: IssueManager) -> None:
        """The child object is unlinked and the refetched parent is returned."""
        mock_parent = _make_issue(3)
        mock_child = _make_issue(5)
        mock_refetched_parent = _make_issue(3)
        mock_issue_manager._repository.get_issue.side_effect = [
            mock_parent,
            mock_child,
            mock_refetched_parent,
        ]

        result = mock_issue_manager.remove_sub_issue(3, 5)

        mock_parent.remove_sub_issue.assert_called_once_with(mock_child)
        mock_parent.add_sub_issue.assert_not_called()
        assert result is mock_refetched_parent

    def test_list_sub_issues_returns_children_in_order(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Children come back in the order the API yields them."""
        mock_parent = _make_issue(3)
        children = [_make_issue(n) for n in (7, 5, 9)]
        mock_parent.get_sub_issues.return_value = iter(children)
        mock_issue_manager._repository.get_issue.return_value = mock_parent

        result = mock_issue_manager.list_sub_issues(3)

        assert result == children

    @pytest.mark.parametrize(
        ("max_results", "expected"),
        [(2, 2), (0, 0), (-1, 0)],
    )
    def test_list_sub_issues_honours_max_results(
        self, mock_issue_manager: IssueManager, max_results: int, expected: int
    ) -> None:
        """The result is capped at max_results; zero and negative yield []."""
        mock_parent = _make_issue(3)
        children = [_make_issue(n) for n in range(10, 15)]
        mock_parent.get_sub_issues.return_value = iter(children)
        mock_issue_manager._repository.get_issue.return_value = mock_parent

        result = mock_issue_manager.list_sub_issues(3, max_results=max_results)

        assert result == children[:expected]

    def test_parent_is_pull_request_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """A pull request as parent is rejected before any write."""
        mock_parent = make_mock_issue(3)  # pull_request stays a truthy Mock
        mock_issue_manager._repository.get_issue.side_effect = [mock_parent]

        with pytest.raises(ValueError, match="#3 is a pull request, not an issue"):
            mock_issue_manager.add_sub_issue(3, 5)

        mock_parent.add_sub_issue.assert_not_called()

    def test_child_is_pull_request_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """A pull request as child is rejected before any write."""
        mock_parent = _make_issue(3)
        mock_child = make_mock_issue(5)  # pull_request stays a truthy Mock
        mock_issue_manager._repository.get_issue.side_effect = [
            mock_parent,
            mock_child,
        ]

        with pytest.raises(ValueError, match="#5 is a pull request, not an issue"):
            mock_issue_manager.add_sub_issue(3, 5)

        mock_parent.add_sub_issue.assert_not_called()

    @pytest.mark.parametrize("bad_number", [0, -1])
    def test_invalid_issue_number_raises(
        self, mock_issue_manager: IssueManager, bad_number: int
    ) -> None:
        """Non-positive numbers are rejected by validate_issue_number."""
        with pytest.raises(ValueError):
            mock_issue_manager.add_sub_issue(bad_number, 5)
        with pytest.raises(ValueError):
            mock_issue_manager.remove_sub_issue(3, bad_number)
        with pytest.raises(ValueError):
            mock_issue_manager.list_sub_issues(bad_number)

    def test_repository_inaccessible_returns_none(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """All three methods return None when the repository is unavailable."""
        with patch.object(mock_issue_manager, "_get_repository", return_value=None):
            assert mock_issue_manager.add_sub_issue(3, 5) is None
            assert mock_issue_manager.remove_sub_issue(3, 5) is None
            assert mock_issue_manager.list_sub_issues(3) is None

    def test_github_exception_propagates(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """A 422 escapes the mixin instead of being swallowed."""
        mock_parent = _make_issue(3)
        mock_child = _make_issue(5)
        mock_parent.add_sub_issue.side_effect = GithubException(
            422,
            {
                "message": "Issue may not contain duplicate sub-issues and "
                "Sub issue may only have one parent"
            },
            None,
        )
        mock_issue_manager._repository.get_issue.side_effect = [
            mock_parent,
            mock_child,
        ]

        with pytest.raises(GithubException) as exc_info:
            mock_issue_manager.add_sub_issue(3, 5)

        assert exc_info.value.status == 422


class TestSubIssueTotal:
    """Tests for sub_issue_total."""

    def test_none_summary_returns_none(self) -> None:
        """A payload without a summary yields None."""
        issue = SimpleNamespace(sub_issues_summary=None)

        assert sub_issue_total(cast(Any, issue)) is None

    def test_summary_total_returned(self) -> None:
        """The summary's total is returned as-is."""
        issue = SimpleNamespace(sub_issues_summary=SimpleNamespace(total=3))

        assert sub_issue_total(cast(Any, issue)) == 3
