"""Unit tests for IssueManager label operations with mocked dependencies."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.issues import IssueManager
from mcp_workspace.github_operations.issues.base import (
    validate_comment_id,
    validate_issue_number,
)


@pytest.mark.git_integration
class TestIssueManagerLabels:
    """Unit tests for IssueManager label operations with mocked dependencies."""

    def test_add_labels_success(self, mock_issue_manager: IssueManager) -> None:
        """Test successful label addition."""
        issue_number = 1
        labels = ["bug", "enhancement"]
        mock_issue = MagicMock()
        mock_issue.number = issue_number

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        mock_issue_manager.add_labels(issue_number, *labels)

        mock_issue.add_to_labels.assert_called_once_with(*labels)

    def test_add_labels_single_label(self, mock_issue_manager: IssueManager) -> None:
        """Test adding a single label."""
        issue_number = 1
        labels = ["bug"]
        mock_issue = MagicMock()

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        mock_issue_manager.add_labels(issue_number, *labels)

        mock_issue.add_to_labels.assert_called_once_with(*labels)

    def test_add_labels_invalid_issue_number(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test adding labels with invalid issue number."""
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            mock_issue_manager.add_labels(0, "bug")

    def test_add_labels_no_labels_provided(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that empty labels list raises ValueError."""
        with pytest.raises(ValueError, match="At least one label must be provided"):
            mock_issue_manager.add_labels(1)

    def test_add_labels_auth_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that authentication errors are raised when adding labels."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.add_labels(1, "bug")

    def test_remove_labels_success(self, mock_issue_manager: IssueManager) -> None:
        """Test successful label removal."""
        issue_number = 1
        labels = ["bug", "enhancement"]
        mock_issue = MagicMock()
        mock_issue.number = issue_number

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        mock_issue_manager.remove_labels(issue_number, *labels)

        mock_issue.remove_from_labels.assert_called_once_with(*labels)

    def test_remove_labels_single_label(self, mock_issue_manager: IssueManager) -> None:
        """Test removing a single label."""
        issue_number = 1
        labels = ["bug"]
        mock_issue = MagicMock()

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        mock_issue_manager.remove_labels(issue_number, *labels)

        mock_issue.remove_from_labels.assert_called_once_with(*labels)

    def test_remove_labels_invalid_issue_number(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test removing labels with invalid issue number."""
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            mock_issue_manager.remove_labels(0, "bug")

    def test_remove_labels_no_labels_provided(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that empty labels list raises ValueError."""
        with pytest.raises(ValueError, match="At least one label must be provided"):
            mock_issue_manager.remove_labels(1)

    def test_remove_labels_auth_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that authentication errors are raised when removing labels."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.remove_labels(1, "bug")

    def test_set_labels_success(self, mock_issue_manager: IssueManager) -> None:
        """Test successful label setting."""
        issue_number = 1
        labels = ["bug", "priority-high"]
        mock_issue = MagicMock()
        mock_issue.number = issue_number

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        mock_issue_manager.set_labels(issue_number, *labels)

        mock_issue.set_labels.assert_called_once_with(*labels)

    def test_set_labels_empty_to_clear_all(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test setting empty labels to clear all labels."""
        issue_number = 1
        mock_issue = MagicMock()

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        mock_issue_manager.set_labels(issue_number)

        mock_issue.set_labels.assert_called_once_with()

    def test_set_labels_single_label(self, mock_issue_manager: IssueManager) -> None:
        """Test setting a single label."""
        issue_number = 1
        labels = ["bug"]
        mock_issue = MagicMock()

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        mock_issue_manager.set_labels(issue_number, *labels)

        mock_issue.set_labels.assert_called_once_with(*labels)

    def test_set_labels_invalid_issue_number(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test setting labels with invalid issue number."""
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            mock_issue_manager.set_labels(0, "bug")

    def test_set_labels_auth_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that authentication errors are raised when setting labels."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.set_labels(1, "bug")


@pytest.mark.git_integration
class TestTransitionIssueLabel:
    """Unit tests for IssueManager.transition_issue_label primitive."""

    def _build_issue_data(self, number: int, labels: List[str]) -> Dict[str, Any]:
        """Helper to build minimal IssueData-shaped dict for get_issue mock."""
        return {
            "number": number,
            "title": "t",
            "body": "",
            "state": "open",
            "labels": labels,
            "assignees": [],
            "user": None,
            "created_at": None,
            "updated_at": None,
            "url": "",
            "locked": False,
        }

    def test_transition_basic_adds_and_clears(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Current={implementing,bug}, new=code_review, clear={implementing,planning}."""
        issue_number = 1
        current = self._build_issue_data(
            issue_number, ["status-06:implementing", "bug"]
        )
        updated = self._build_issue_data(issue_number, ["status-07:code-review", "bug"])

        with (
            patch.object(IssueManager, "get_issue", return_value=current) as mock_get,
            patch.object(IssueManager, "set_labels", return_value=updated) as mock_set,
        ):
            result = mock_issue_manager.transition_issue_label(
                issue_number,
                "status-07:code-review",
                labels_to_clear=["status-06:implementing", "status-03:planning"],
            )

        assert result is True
        mock_get.assert_called_once_with(issue_number)
        mock_set.assert_called_once()
        call_args = mock_set.call_args
        assert call_args.args[0] == issue_number
        assert set(call_args.args[1:]) == {"status-07:code-review", "bug"}

    def test_transition_idempotent_noop_when_target_present_and_no_overlap(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Target present + no overlap with clear set → no set_labels call."""
        issue_number = 1
        current = self._build_issue_data(issue_number, ["status-07:code-review", "bug"])

        with (
            patch.object(IssueManager, "get_issue", return_value=current),
            patch.object(IssueManager, "set_labels") as mock_set,
        ):
            result = mock_issue_manager.transition_issue_label(
                issue_number,
                "status-07:code-review",
                labels_to_clear=["status-06:implementing"],
            )

        assert result is True
        mock_set.assert_not_called()

    def test_transition_clears_stray_labels(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Target present, stray label in clear set → strips stray."""
        issue_number = 1
        current = self._build_issue_data(
            issue_number, ["status-07:code-review", "status-03:planning"]
        )
        updated = self._build_issue_data(issue_number, ["status-07:code-review"])

        with (
            patch.object(IssueManager, "get_issue", return_value=current),
            patch.object(IssueManager, "set_labels", return_value=updated) as mock_set,
        ):
            result = mock_issue_manager.transition_issue_label(
                issue_number,
                "status-07:code-review",
                labels_to_clear=["status-06:implementing", "status-03:planning"],
            )

        assert result is True
        mock_set.assert_called_once()
        call_args = mock_set.call_args
        assert call_args.args[0] == issue_number
        assert set(call_args.args[1:]) == {"status-07:code-review"}

    def test_transition_empty_labels_to_clear_just_adds_new(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Empty clear set → just adds new_label to current."""
        issue_number = 1
        current = self._build_issue_data(issue_number, ["bug"])
        updated = self._build_issue_data(issue_number, ["bug", "status-07:code-review"])

        with (
            patch.object(IssueManager, "get_issue", return_value=current),
            patch.object(IssueManager, "set_labels", return_value=updated) as mock_set,
        ):
            result = mock_issue_manager.transition_issue_label(
                issue_number, "status-07:code-review"
            )

        assert result is True
        mock_set.assert_called_once()
        call_args = mock_set.call_args
        assert call_args.args[0] == issue_number
        assert set(call_args.args[1:]) == {"bug", "status-07:code-review"}

    def test_transition_invalid_issue_number_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """issue_number=0 → ValueError propagates."""
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            mock_issue_manager.transition_issue_label(0, "status-07:code-review")

    def test_transition_auth_error_reraises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """GithubException(401) from get_issue → re-raised by decorator."""
        with patch.object(
            IssueManager,
            "get_issue",
            side_effect=GithubException(401, {"message": "Bad credentials"}, None),
        ):
            with pytest.raises(GithubException):
                mock_issue_manager.transition_issue_label(
                    1,
                    "status-07:code-review",
                    labels_to_clear=["status-06:implementing"],
                )

    def test_transition_set_labels_failure_returns_false(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """set_labels returns empty IssueData (number=0) → primitive returns False."""
        issue_number = 1
        current = self._build_issue_data(issue_number, ["bug"])
        empty = self._build_issue_data(0, [])

        with (
            patch.object(IssueManager, "get_issue", return_value=current),
            patch.object(IssueManager, "set_labels", return_value=empty),
        ):
            result = mock_issue_manager.transition_issue_label(
                issue_number, "status-07:code-review"
            )

        assert result is False

    def test_transition_get_issue_failure_returns_false(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """get_issue returns empty IssueData (number=0) → primitive returns False, set_labels not called."""
        from mcp_workspace.github_operations.issues.types import (
            create_empty_issue_data,
        )

        with (
            patch.object(
                IssueManager, "get_issue", return_value=create_empty_issue_data()
            ),
            patch.object(IssueManager, "set_labels") as mock_set,
        ):
            result = mock_issue_manager.transition_issue_label(
                1, "status-07:code-review", labels_to_clear=["status-06:implementing"]
            )

        assert result is False
        mock_set.assert_not_called()
