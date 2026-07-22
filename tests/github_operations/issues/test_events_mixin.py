"""Unit tests for IssueManager event operations with mocked dependencies."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.issues import IssueEventType, IssueManager
from mcp_workspace.github_operations.issues.base import (
    validate_comment_id,
    validate_issue_number,
)


@pytest.mark.git_integration
class TestIssueManagerEvents:
    """Unit tests for IssueManager event and timeline operations with mocked dependencies."""

    def test_get_issue_events_success(self, mock_issue_manager: IssueManager) -> None:
        """Test successful issue events retrieval."""
        issue_number = 1
        mock_issue = MagicMock()
        mock_event1 = MagicMock()
        mock_event1.event = "labeled"
        mock_event1.created_at = datetime(2023, 1, 1)
        mock_event2 = MagicMock()
        mock_event2.event = "closed"
        mock_event2.created_at = datetime(2023, 1, 2)

        mock_issue_manager._repository.get_issue.return_value = mock_issue
        mock_issue.get_events.return_value = [mock_event1, mock_event2]

        result = mock_issue_manager.get_issue_events(issue_number)

        assert len(result) == 2
        assert result[0]["event"] == "labeled"
        assert result[1]["event"] == "closed"

    def test_get_issue_events_invalid_issue_number(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test getting events with invalid issue number."""
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            mock_issue_manager.get_issue_events(0)

    def test_get_issue_events_filter_label_events(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test filtering for labeled events only."""
        issue_number = 1
        mock_issue = MagicMock()
        mock_labeled_event = MagicMock()
        mock_labeled_event.event = "labeled"
        mock_labeled_event.label = MagicMock()
        mock_labeled_event.label.name = "bug"
        mock_closed_event = MagicMock()
        mock_closed_event.event = "closed"

        mock_issue_manager._repository.get_issue.return_value = mock_issue
        mock_issue.get_events.return_value = [mock_labeled_event, mock_closed_event]

        result = mock_issue_manager.get_issue_events(
            issue_number, event_type=IssueEventType.LABELED
        )

        assert len(result) == 1
        assert result[0]["event"] == "labeled"

    def test_get_issue_events_api_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that API errors are raised when getting events."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            500, {"message": "Internal server error"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.get_issue_events(1)

    def test_get_issue_events_filter_unlabeled(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test filtering for unlabeled events."""
        issue_number = 1
        mock_issue = MagicMock()
        mock_unlabeled_event = MagicMock()
        mock_unlabeled_event.event = "unlabeled"
        mock_unlabeled_event.label = MagicMock()
        mock_unlabeled_event.label.name = "bug"
        mock_labeled_event = MagicMock()
        mock_labeled_event.event = "labeled"

        mock_issue_manager._repository.get_issue.return_value = mock_issue
        mock_issue.get_events.return_value = [mock_unlabeled_event, mock_labeled_event]

        result = mock_issue_manager.get_issue_events(
            issue_number, event_type=IssueEventType.UNLABELED
        )

        assert len(result) == 1
        assert result[0]["event"] == "unlabeled"

    def test_get_issue_events_empty_events(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test getting events from issue with no events."""
        issue_number = 1
        mock_issue = MagicMock()

        mock_issue_manager._repository.get_issue.return_value = mock_issue
        mock_issue.get_events.return_value = []

        result = mock_issue_manager.get_issue_events(issue_number)

        assert len(result) == 0
