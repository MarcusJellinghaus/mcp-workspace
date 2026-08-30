"""Tests for the linked-branch state collected onto the branch status report.

Covers `_collect_linked_branch_status`, the `linked_branch_blocks` predicate
and the wiring that carries both new fields onto `BranchStatusReport`.
Nothing renders and nothing blocks in this step.
"""

from pathlib import Path
from typing import List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.checks.branch_status import (
    _collect_linked_branch_status,
    collect_branch_status,
)
from mcp_workspace.checks.branch_status_rendering import (
    CIStatus,
    LinkedBranchStatus,
    linked_branch_blocks,
)
from mcp_workspace.workflows.task_tracker import TaskTrackerStatus


class TestCollectLinkedBranchStatus:
    """State matrix for `_collect_linked_branch_status`."""

    @pytest.mark.parametrize(
        "linked, expected",
        [
            (["255-feature"], (LinkedBranchStatus.OK, ("255-feature",))),
            (["255-old"], (LinkedBranchStatus.MISMATCH, ("255-old",))),
            (
                ["255-a", "255-b"],
                (LinkedBranchStatus.AMBIGUOUS, ("255-a", "255-b")),
            ),
            ([], (LinkedBranchStatus.NOT_LINKED, ())),
            (None, (LinkedBranchStatus.UNKNOWN, ())),
        ],
    )
    @patch("mcp_workspace.checks.branch_status.IssueBranchManager")
    def test_state_matrix(
        self,
        mock_mgr_cls: MagicMock,
        linked: Optional[List[str]],
        expected: Tuple[LinkedBranchStatus, Tuple[str, ...]],
    ) -> None:
        mock_mgr = MagicMock()
        mock_mgr.get_linked_branches_or_none.return_value = linked
        mock_mgr_cls.return_value = mock_mgr

        result = _collect_linked_branch_status(Path("/tmp"), "255-feature")

        assert result == expected
        mock_mgr.get_linked_branches_or_none.assert_called_once_with(255)

    @patch("mcp_workspace.checks.branch_status.IssueBranchManager")
    def test_non_issue_branch_is_not_checked_and_makes_no_request(
        self, mock_mgr_cls: MagicMock
    ) -> None:
        """A branch name with no issue number costs zero requests."""
        result = _collect_linked_branch_status(Path("/tmp"), "main")

        assert result == (LinkedBranchStatus.NOT_CHECKED, ())
        mock_mgr_cls.assert_not_called()

    @patch("mcp_workspace.checks.branch_status.IssueBranchManager")
    def test_manager_init_failure_is_unknown(self, mock_mgr_cls: MagicMock) -> None:
        """`IssueBranchManager.__init__` raises without a token — not a crash."""
        mock_mgr_cls.side_effect = ValueError("no token")

        result = _collect_linked_branch_status(Path("/tmp"), "255-feature")

        assert result == (LinkedBranchStatus.UNKNOWN, ())

    @patch("mcp_workspace.checks.branch_status.IssueBranchManager")
    def test_lookup_exception_is_unknown(self, mock_mgr_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_mgr.get_linked_branches_or_none.side_effect = RuntimeError("boom")
        mock_mgr_cls.return_value = mock_mgr

        result = _collect_linked_branch_status(Path("/tmp"), "255-feature")

        assert result == (LinkedBranchStatus.UNKNOWN, ())


class TestLinkedBranchWiring:
    """The collected state reaches the report."""

    @patch("mcp_workspace.checks.branch_status._collect_pr_info")
    @patch("mcp_workspace.checks.branch_status._collect_github_label")
    @patch("mcp_workspace.checks.branch_status._collect_task_status")
    @patch("mcp_workspace.checks.branch_status._collect_rebase_status")
    @patch("mcp_workspace.checks.branch_status._collect_ci_status")
    @patch("mcp_workspace.checks.branch_status.detect_base_branch")
    @patch("mcp_workspace.checks.branch_status.PullRequestManager")
    @patch("mcp_workspace.checks.branch_status.IssueManager")
    @patch("mcp_workspace.checks.branch_status.get_current_branch_name")
    @patch("mcp_workspace.checks.branch_status._collect_linked_branch_status")
    def test_report_carries_linked_branch_state(
        self,
        mock_linked: MagicMock,
        mock_branch: MagicMock,
        mock_issue_mgr_cls: MagicMock,
        mock_pr_mgr_cls: MagicMock,
        mock_detect: MagicMock,
        mock_ci: MagicMock,
        mock_rebase: MagicMock,
        mock_tasks: MagicMock,
        mock_label: MagicMock,
        mock_pr_info: MagicMock,
    ) -> None:
        mock_linked.return_value = (LinkedBranchStatus.MISMATCH, ("255-old",))
        mock_branch.return_value = "255-feature"
        mock_issue_mgr = MagicMock()
        mock_issue_mgr.get_issue.return_value = {"number": 255, "labels": []}
        mock_issue_mgr_cls.return_value = mock_issue_mgr
        mock_pr_mgr_cls.return_value = MagicMock()
        mock_detect.return_value = "main"
        mock_ci.return_value = (CIStatus.PASSED, None, [])
        mock_rebase.return_value = (False, "up-to-date")
        mock_tasks.return_value = (TaskTrackerStatus.COMPLETE, "done", False)
        mock_label.return_value = "unknown"
        mock_pr_info.return_value = (45, "https://url", True, True, "clean")

        report = collect_branch_status(Path("/tmp"))

        assert report.linked_branch_status == LinkedBranchStatus.MISMATCH
        assert report.linked_branches == ("255-old",)


class TestLinkedBranchBlocks:
    """The single source of truth for 'does this state block'."""

    @pytest.mark.parametrize(
        "status, expected",
        [
            (LinkedBranchStatus.OK, False),
            (LinkedBranchStatus.NOT_CHECKED, False),
            (LinkedBranchStatus.MISMATCH, True),
            (LinkedBranchStatus.AMBIGUOUS, True),
            (LinkedBranchStatus.NOT_LINKED, True),
            (LinkedBranchStatus.UNKNOWN, True),
        ],
    )
    def test_blocking_states(self, status: LinkedBranchStatus, expected: bool) -> None:
        assert linked_branch_blocks(status) is expected
