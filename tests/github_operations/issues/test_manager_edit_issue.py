"""Unit tests for IssueManager.edit_issue with mocked dependencies."""

from datetime import datetime
from typing import List, Optional
from unittest.mock import MagicMock

import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.issues import IssueManager

from .._issue_test_helpers import make_mock_issue


def _make_named(name: str) -> MagicMock:
    """Create a mock with a ``name`` attribute (not settable via constructor)."""
    named = MagicMock()
    named.name = name
    return named


def _make_editable_issue(
    number: int = 1,
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
) -> MagicMock:
    """Create a mock issue carrying every attribute _issue_to_data reads."""
    issue = make_mock_issue(number)
    issue.title = "Test Issue"
    issue.body = "Test body"
    issue.state = "open"
    issue.labels = [_make_named(label) for label in (labels or [])]
    issue.assignees = [MagicMock(login=login) for login in (assignees or [])]
    issue.user.login = "testuser"
    issue.created_at = datetime(2023, 1, 1)
    issue.updated_at = datetime(2023, 1, 2)
    issue.html_url = f"https://github.com/test/repo/issues/{number}"
    issue.locked = False
    return issue


@pytest.mark.git_integration
class TestIssueManagerEditIssue:
    """Unit tests for the combined edit_issue operation."""

    def test_edit_issue_scalars_only(self, mock_issue_manager: IssueManager) -> None:
        """Title and body go into a single edit() call, no collection calls."""
        issue = _make_editable_issue(labels=["bug"])
        mock_issue_manager._repository.get_issue.return_value = issue

        result = mock_issue_manager.edit_issue(1, title="New title", body="New body")

        issue.edit.assert_called_once_with(title="New title", body="New body")
        issue.add_to_labels.assert_not_called()
        issue.remove_from_labels.assert_not_called()
        issue.add_to_assignees.assert_not_called()
        assert result["number"] == 1

    def test_edit_issue_no_arguments_skips_edit(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """With nothing to change, edit() is not called but data is refetched."""
        issue = _make_editable_issue(labels=["bug"])
        mock_issue_manager._repository.get_issue.return_value = issue

        result = mock_issue_manager.edit_issue(1)

        issue.edit.assert_not_called()
        assert result["number"] == 1
        assert result["labels"] == ["bug"]

    def test_edit_issue_state_shares_the_scalar_call(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """state is passed inside the same edit() call as the other scalars."""
        issue = _make_editable_issue()
        mock_issue_manager._repository.get_issue.return_value = issue

        mock_issue_manager.edit_issue(1, title="New title", state="closed")

        issue.edit.assert_called_once_with(title="New title", state="closed")

    def test_edit_issue_invalid_state_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """An unsupported state is rejected before any API call."""
        issue = _make_editable_issue()
        mock_issue_manager._repository.get_issue.return_value = issue

        with pytest.raises(ValueError, match="Issue state must be 'open' or 'closed'"):
            mock_issue_manager.edit_issue(1, state="bogus")

    def test_edit_issue_add_labels_uses_varargs(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """All added labels go out in one add_to_labels call."""
        issue = _make_editable_issue()
        mock_issue_manager._repository.get_issue.return_value = issue

        mock_issue_manager.edit_issue(1, add_labels=["a", "b"])

        issue.add_to_labels.assert_called_once_with("a", "b")

    def test_edit_issue_remove_labels_filters_absent(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Only labels actually on the issue are removed."""
        issue = _make_editable_issue(labels=["bug"])
        mock_issue_manager._repository.get_issue.return_value = issue

        mock_issue_manager.edit_issue(1, remove_labels=["bug", "absent"])

        issue.remove_from_labels.assert_called_once_with("bug")

    def test_edit_issue_remove_labels_all_absent_is_noop(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """A removal of labels the issue does not carry is not an error."""
        issue = _make_editable_issue(labels=["bug"])
        mock_issue_manager._repository.get_issue.return_value = issue

        result = mock_issue_manager.edit_issue(1, remove_labels=["x", "y"])

        issue.remove_from_labels.assert_not_called()
        assert result["number"] == 1

    def test_edit_issue_remove_labels_matches_case_insensitively(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Removing "Bug" detaches the repository's "bug" instead of doing nothing.

        GitHub matches label names case-insensitively, and the tool-layer guard
        accepts a differently-cased name, so an exact-match filter here would
        silently skip the removal while the tool reported success.
        """
        issue = _make_editable_issue(labels=["bug"])
        mock_issue_manager._repository.get_issue.return_value = issue

        mock_issue_manager.edit_issue(1, remove_labels=["Bug"])

        # Removed under the repository's own casing, not the caller's
        issue.remove_from_labels.assert_called_once_with("bug")

    def test_edit_issue_records_attempted_writes(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Every write call is recorded, in order, for the caller to inspect."""
        issue = _make_editable_issue(labels=["bug"])
        mock_issue_manager._repository.get_issue.return_value = issue
        attempted: List[str] = []

        mock_issue_manager.edit_issue(
            1,
            title="New title",
            add_labels=["enhancement"],
            remove_labels=["bug"],
            add_assignees=["alice"],
            attempted_writes=attempted,
        )

        assert attempted == ["scalars", "add_labels", "remove_labels", "add_assignees"]

    def test_edit_issue_records_nothing_when_opening_fetch_fails(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """A failed opening fetch leaves the log empty: nothing was written."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            422, {"message": "Unprocessable Entity"}, None
        )
        attempted: List[str] = []

        mock_issue_manager.edit_issue(1, title="New title", attempted_writes=attempted)

        assert attempted == []

    def test_edit_issue_records_no_op_removal_as_no_write(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """A removal filtered out entirely issues no call, so it logs nothing."""
        issue = _make_editable_issue(labels=["bug"])
        mock_issue_manager._repository.get_issue.return_value = issue
        attempted: List[str] = []

        mock_issue_manager.edit_issue(
            1, remove_labels=["absent"], attempted_writes=attempted
        )

        assert attempted == []

    def test_edit_issue_add_assignees(self, mock_issue_manager: IssueManager) -> None:
        """Assignees are added with a single varargs call."""
        issue = _make_editable_issue(assignees=["alice"])
        mock_issue_manager._repository.get_issue.return_value = issue

        result = mock_issue_manager.edit_issue(1, add_assignees=["alice"])

        issue.add_to_assignees.assert_called_once_with("alice")
        assert result["assignees"] == ["alice"]

    def test_edit_issue_fetches_issue_exactly_twice(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """A full edit costs one fetch up front and one refetch, nothing more."""
        issue = _make_editable_issue(labels=["bug"])
        mock_issue_manager._repository.get_issue.return_value = issue

        mock_issue_manager.edit_issue(
            1,
            title="New title",
            add_labels=["enhancement"],
            remove_labels=["bug"],
            add_assignees=["alice"],
        )

        assert mock_issue_manager._repository.get_issue.call_count == 2

    def test_edit_issue_invalid_issue_number_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """An invalid issue number raises rather than returning empty data."""
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            mock_issue_manager.edit_issue(0, title="New title")

    def test_edit_issue_swallowed_error_returns_empty(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """A 422 is swallowed by the decorator and reported as empty IssueData."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            422, {"message": "Unprocessable Entity"}, None
        )

        result = mock_issue_manager.edit_issue(1, title="New title")

        assert result["number"] == 0

    def test_edit_issue_failures_return_distinct_dicts(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """The callable default_return yields a fresh dict per failure."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            422, {"message": "Unprocessable Entity"}, None
        )

        first = mock_issue_manager.edit_issue(1, title="First")
        second = mock_issue_manager.edit_issue(1, title="Second")

        assert first == second
        assert first is not second
