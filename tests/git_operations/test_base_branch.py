"""Tests for base_branch detection module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.git_operations.base_branch import (
    _detect_from_issue,
    _detect_from_merge_base,
    _detect_from_pr,
    detect_base_branch,
)
from mcp_workspace.github_operations.issues.types import IssueData

# ---------------------------------------------------------------------------
# _detect_from_issue tests
# ---------------------------------------------------------------------------


class TestDetectFromIssue:
    """Tests for _detect_from_issue helper."""

    def test_returns_base_branch_from_issue_data(self) -> None:
        """If issue_data has base_branch, return it directly."""
        issue_data = IssueData(
            number=42,
            title="test",
            body="",
            state="open",
            labels=[],
            assignees=[],
            user=None,
            created_at=None,
            updated_at=None,
            url="",
            locked=False,
            author_association="OWNER",
            base_branch="develop",
        )
        result = _detect_from_issue(issue_data)
        assert result == "develop"

    def test_returns_none_when_issue_data_has_no_base_branch(self) -> None:
        """If issue_data exists but has no base_branch, return None."""
        issue_data = IssueData(
            number=42,
            title="test",
            body="",
            state="open",
            labels=[],
            assignees=[],
            user=None,
            created_at=None,
            updated_at=None,
            url="",
            locked=False,
            author_association="OWNER",
        )
        result = _detect_from_issue(issue_data)
        assert result is None

    def test_returns_none_when_issue_data_is_none(self) -> None:
        """If no issue_data is provided, return None."""
        result = _detect_from_issue(None)
        assert result is None


# ---------------------------------------------------------------------------
# _detect_from_pr tests
# ---------------------------------------------------------------------------


class TestDetectFromPr:
    """Tests for _detect_from_pr helper."""

    def test_returns_base_branch_from_pr(self) -> None:
        """If PR found with base_branch, return it."""
        mock_pr_manager = MagicMock()
        mock_pr_manager.find_pull_request_by_head.return_value = [
            {
                "number": 10,
                "title": "PR title",
                "body": "",
                "state": "open",
                "head_branch": "42-feature",
                "base_branch": "develop",
                "url": "",
                "created_at": None,
                "updated_at": None,
                "user": None,
                "mergeable": True,
                "merged": False,
                "draft": False,
            }
        ]
        result = _detect_from_pr("42-feature", mock_pr_manager)
        assert result == "develop"

    def test_returns_none_when_no_prs_found(self) -> None:
        """If no PRs found for branch, return None."""
        mock_pr_manager = MagicMock()
        mock_pr_manager.find_pull_request_by_head.return_value = []
        result = _detect_from_pr("42-feature", mock_pr_manager)
        assert result is None

    def test_returns_none_when_pr_manager_is_none(self) -> None:
        """If pr_manager not provided, return None."""
        result = _detect_from_pr("42-feature", None)
        assert result is None

    def test_returns_none_when_pr_manager_raises(self) -> None:
        """If pr_manager raises, catch and return None."""
        mock_pr_manager = MagicMock()
        mock_pr_manager.find_pull_request_by_head.side_effect = RuntimeError("API err")
        result = _detect_from_pr("42-feature", mock_pr_manager)
        assert result is None


# ---------------------------------------------------------------------------
# _detect_from_merge_base tests
# ---------------------------------------------------------------------------


class TestDetectFromMergeBase:
    """Tests for _detect_from_merge_base helper."""

    @patch(
        "mcp_workspace.git_operations.base_branch.detect_parent_branch_via_merge_base"
    )
    def test_returns_parent_branch(self, mock_detect: MagicMock) -> None:
        """If merge-base finds a parent, return it."""
        mock_detect.return_value = "main"
        result = _detect_from_merge_base(Path("/repo"), "feature-branch")
        assert result == "main"

    @patch(
        "mcp_workspace.git_operations.base_branch.detect_parent_branch_via_merge_base"
    )
    def test_returns_none_when_no_parent(self, mock_detect: MagicMock) -> None:
        """If merge-base finds nothing, return None."""
        mock_detect.return_value = None
        result = _detect_from_merge_base(Path("/repo"), "feature-branch")
        assert result is None


# ---------------------------------------------------------------------------
# detect_base_branch integration tests
# ---------------------------------------------------------------------------


class TestDetectBaseBranch:
    """Tests for the main detect_base_branch function."""

    @patch("mcp_workspace.git_operations.base_branch.get_current_branch_name")
    def test_returns_none_on_detached_head(self, mock_get_branch: MagicMock) -> None:
        """If current branch is None (detached HEAD), return None."""
        mock_get_branch.return_value = None
        result = detect_base_branch(Path("/repo"))
        assert result is None

    @patch("mcp_workspace.git_operations.base_branch.get_current_branch_name")
    def test_uses_provided_current_branch(self, mock_get_branch: MagicMock) -> None:
        """If current_branch is provided, don't auto-detect."""
        issue_data = IssueData(
            number=42,
            title="test",
            body="",
            state="open",
            labels=[],
            assignees=[],
            user=None,
            created_at=None,
            updated_at=None,
            url="",
            locked=False,
            author_association="OWNER",
            base_branch="develop",
        )
        result = detect_base_branch(
            Path("/repo"), current_branch="42-feature", issue_data=issue_data
        )
        assert result == "develop"
        mock_get_branch.assert_not_called()

    @patch("mcp_workspace.git_operations.base_branch.get_default_branch_name")
    @patch(
        "mcp_workspace.git_operations.base_branch.detect_parent_branch_via_merge_base"
    )
    @patch("mcp_workspace.git_operations.base_branch.get_current_branch_name")
    def test_priority_issue_over_pr(
        self,
        mock_get_branch: MagicMock,
        mock_merge_base: MagicMock,
        mock_default: MagicMock,
    ) -> None:
        """Issue base_branch takes priority over PR and merge-base."""
        mock_get_branch.return_value = "42-feature"
        issue_data = IssueData(
            number=42,
            title="test",
            body="",
            state="open",
            labels=[],
            assignees=[],
            user=None,
            created_at=None,
            updated_at=None,
            url="",
            locked=False,
            author_association="OWNER",
            base_branch="from-issue",
        )
        mock_pr_manager = MagicMock()
        mock_pr_manager.find_pull_request_by_head.return_value = [
            {"base_branch": "from-pr", "number": 1}
        ]
        result = detect_base_branch(
            Path("/repo"),
            issue_data=issue_data,
            pr_manager=mock_pr_manager,
        )
        assert result == "from-issue"
        mock_pr_manager.find_pull_request_by_head.assert_not_called()
        mock_merge_base.assert_not_called()

    @patch("mcp_workspace.git_operations.base_branch.get_default_branch_name")
    @patch(
        "mcp_workspace.git_operations.base_branch.detect_parent_branch_via_merge_base"
    )
    @patch("mcp_workspace.git_operations.base_branch.get_current_branch_name")
    def test_priority_pr_over_merge_base(
        self,
        mock_get_branch: MagicMock,
        mock_merge_base: MagicMock,
        mock_default: MagicMock,
    ) -> None:
        """PR base_branch takes priority over merge-base."""
        mock_get_branch.return_value = "feature-no-issue"
        mock_pr_manager = MagicMock()
        mock_pr_manager.find_pull_request_by_head.return_value = [
            {"base_branch": "from-pr", "number": 5}
        ]
        result = detect_base_branch(
            Path("/repo"),
            pr_manager=mock_pr_manager,
        )
        assert result == "from-pr"
        mock_merge_base.assert_not_called()

    @patch("mcp_workspace.git_operations.base_branch.get_default_branch_name")
    @patch(
        "mcp_workspace.git_operations.base_branch.detect_parent_branch_via_merge_base"
    )
    @patch("mcp_workspace.git_operations.base_branch.get_current_branch_name")
    def test_falls_back_to_merge_base(
        self,
        mock_get_branch: MagicMock,
        mock_merge_base: MagicMock,
        mock_default: MagicMock,
    ) -> None:
        """Falls back to merge-base when issue and PR detection fail."""
        mock_get_branch.return_value = "feature-branch"
        mock_merge_base.return_value = "develop"
        result = detect_base_branch(Path("/repo"))
        assert result == "develop"
        mock_default.assert_not_called()

    @patch("mcp_workspace.git_operations.base_branch.get_default_branch_name")
    @patch(
        "mcp_workspace.git_operations.base_branch.detect_parent_branch_via_merge_base"
    )
    @patch("mcp_workspace.git_operations.base_branch.get_current_branch_name")
    def test_falls_back_to_default_branch(
        self,
        mock_get_branch: MagicMock,
        mock_merge_base: MagicMock,
        mock_default: MagicMock,
    ) -> None:
        """Falls back to default branch when all other methods fail."""
        mock_get_branch.return_value = "feature-branch"
        mock_merge_base.return_value = None
        mock_default.return_value = "main"
        result = detect_base_branch(Path("/repo"))
        assert result == "main"

    @patch("mcp_workspace.git_operations.base_branch.get_default_branch_name")
    @patch(
        "mcp_workspace.git_operations.base_branch.detect_parent_branch_via_merge_base"
    )
    @patch("mcp_workspace.git_operations.base_branch.get_current_branch_name")
    def test_returns_none_when_all_fail(
        self,
        mock_get_branch: MagicMock,
        mock_merge_base: MagicMock,
        mock_default: MagicMock,
    ) -> None:
        """Returns None when all detection methods fail."""
        mock_get_branch.return_value = "feature-branch"
        mock_merge_base.return_value = None
        mock_default.return_value = None
        result = detect_base_branch(Path("/repo"))
        assert result is None
