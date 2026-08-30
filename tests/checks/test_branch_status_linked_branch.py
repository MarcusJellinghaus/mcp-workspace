"""Tests for the linked-branch state collected onto the branch status report.

Covers `_collect_linked_branch_status`, the `linked_branch_blocks` predicate,
the wiring that carries both new fields onto `BranchStatusReport`, and the
rendering / review-gate / merge-verdict consequences of a non-OK state.
"""

from pathlib import Path
from typing import Callable, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.checks.branch_status import (
    BranchStatusReport,
    _collect_linked_branch_status,
    collect_branch_status,
)
from mcp_workspace.checks.branch_status_rendering import (
    CIStatus,
    LinkedBranchStatus,
    _format_linked_branch_line,
    _review_gate_header,
    format_report_for_human,
    format_report_for_llm,
    linked_branch_blocks,
)
from mcp_workspace.workflows.task_tracker import TaskTrackerStatus

Formatter = Callable[[BranchStatusReport], str]

_FORMATTERS: List[Formatter] = [format_report_for_human, format_report_for_llm]


def _make_report(
    linked_branch_status: LinkedBranchStatus,
    linked_branches: Tuple[str, ...] = (),
    branch_name: str = "255-feature",
    ci_status: CIStatus = CIStatus.PASSED,
) -> BranchStatusReport:
    """Build an otherwise-clean report carrying the given linked-branch state."""
    return BranchStatusReport(
        branch_name=branch_name,
        base_branch="main",
        ci_status=ci_status,
        ci_details=None,
        rebase_needed=False,
        rebase_reason="up-to-date",
        tasks_status=TaskTrackerStatus.COMPLETE,
        tasks_reason="All tasks complete",
        tasks_is_blocking=False,
        current_github_label="status-04:in-progress",
        recommendations=[],
        linked_branch_status=linked_branch_status,
        linked_branches=linked_branches,
    )


def _linked_lines(rendered: str) -> List[str]:
    """Return every ``Linked Branch:`` line in a rendered report."""
    return [
        line for line in rendered.splitlines() if line.startswith("Linked Branch:")
    ]


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


class TestLinkedBranchRendering:
    """The `Linked Branch: ...` line in both formatters."""

    @pytest.mark.parametrize("formatter", _FORMATTERS)
    @pytest.mark.parametrize(
        "status, linked, expected_substrings",
        [
            (LinkedBranchStatus.OK, ("255-feature",), ["255-feature"]),
            (
                LinkedBranchStatus.MISMATCH,
                ("255-old",),
                ["#255", "255-old", "255-feature"],
            ),
            (
                LinkedBranchStatus.AMBIGUOUS,
                ("255-old", "255-feature"),
                ["#255", "255-old", "255-feature", "2 branches"],
            ),
            (LinkedBranchStatus.NOT_LINKED, (), ["#255", "255-feature"]),
            (LinkedBranchStatus.UNKNOWN, (), ["#255", "could not determine"]),
        ],
    )
    def test_state_renders_one_line(
        self,
        status: LinkedBranchStatus,
        linked: Tuple[str, ...],
        expected_substrings: List[str],
        formatter: Formatter,
    ) -> None:
        rendered = formatter(_make_report(status, linked))

        lines = _linked_lines(rendered)
        assert len(lines) == 1
        assert lines[0].startswith(f"Linked Branch: {status.value}")
        for substring in expected_substrings:
            assert substring in lines[0]

    @pytest.mark.parametrize("formatter", _FORMATTERS)
    def test_not_checked_renders_no_line(self, formatter: Formatter) -> None:
        rendered = formatter(_make_report(LinkedBranchStatus.NOT_CHECKED))

        assert _linked_lines(rendered) == []

    @pytest.mark.parametrize("formatter", _FORMATTERS)
    def test_branch_without_issue_number_renders_no_line(
        self, formatter: Formatter
    ) -> None:
        """The issue number guard suppresses the line even for a blocking state."""
        report = _make_report(
            LinkedBranchStatus.MISMATCH, ("255-old",), branch_name="feature"
        )

        assert _linked_lines(formatter(report)) == []
        assert _format_linked_branch_line(report) is None

    def test_message_stays_repo_neutral_and_names_the_panel(self) -> None:
        """Wording never claims the linked branch lives in this repository."""
        line = _format_linked_branch_line(
            _make_report(LinkedBranchStatus.MISMATCH, ("255-old",))
        )

        assert line is not None
        assert "Development panel" in line
        assert "lookup failed" not in line


class TestLinkedBranchReviewGate:
    """`Review Gate: BLOCKED (linked branch)` and its precedence."""

    @pytest.mark.parametrize(
        "status",
        [
            LinkedBranchStatus.MISMATCH,
            LinkedBranchStatus.AMBIGUOUS,
            LinkedBranchStatus.NOT_LINKED,
            LinkedBranchStatus.UNKNOWN,
        ],
    )
    def test_blocking_states_block_the_gate(self, status: LinkedBranchStatus) -> None:
        header = _review_gate_header(_make_report(status), fail_on_reviews=True)

        assert header == "Review Gate: BLOCKED (linked branch)"

    def test_unknown_renders_blocked_not_unknown(self) -> None:
        """Deliberate: every non-OK state blocks, including UNKNOWN."""
        header = _review_gate_header(
            _make_report(LinkedBranchStatus.UNKNOWN), fail_on_reviews=True
        )

        assert header == "Review Gate: BLOCKED (linked branch)"
        assert "UNKNOWN" not in header

    def test_ci_unavailable_takes_precedence(self) -> None:
        report = _make_report(
            LinkedBranchStatus.MISMATCH,
            ("255-old",),
            ci_status=CIStatus.UNAVAILABLE,
        )

        assert (
            _review_gate_header(report, fail_on_reviews=True)
            == "Review Gate: UNKNOWN (no token)"
        )

    def test_ci_unknown_takes_precedence(self) -> None:
        report = _make_report(
            LinkedBranchStatus.MISMATCH,
            ("255-old",),
            ci_status=CIStatus.UNKNOWN,
        )

        assert (
            _review_gate_header(report, fail_on_reviews=True)
            == "Review Gate: UNKNOWN (undeterminable)"
        )

    def test_gate_off_renders_nothing(self) -> None:
        report = _make_report(LinkedBranchStatus.MISMATCH, ("255-old",))

        assert _review_gate_header(report, fail_on_reviews=False) is None

    @pytest.mark.parametrize(
        "status, linked",
        [
            (LinkedBranchStatus.OK, ("255-feature",)),
            (LinkedBranchStatus.NOT_CHECKED, ()),
        ],
    )
    def test_non_blocking_states_stay_clean(
        self, status: LinkedBranchStatus, linked: Tuple[str, ...]
    ) -> None:
        header = _review_gate_header(_make_report(status, linked), fail_on_reviews=True)

        assert header == "Review Gate: clean"


class TestLinkedBranchSuppressesMergeVerdict:
    """End-to-end: the collected state reaches `_generate_recommendations`.

    The recommendation-level tests use hand-built dicts, so only a run through
    `collect_branch_status` proves the `report_data` key written by the
    collector is the key the recommendation chain reads.
    """

    @staticmethod
    def _collect(mocks: Tuple[MagicMock, ...]) -> BranchStatusReport:
        (
            mock_branch,
            mock_issue_mgr_cls,
            mock_pr_mgr_cls,
            mock_detect,
            mock_ci,
            mock_rebase,
            mock_tasks,
            mock_label,
            mock_pr_info,
        ) = mocks
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
        return collect_branch_status(Path("/tmp"))

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
    def test_mismatch_suppresses_ready_to_merge(
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

        report = self._collect(
            (
                mock_branch,
                mock_issue_mgr_cls,
                mock_pr_mgr_cls,
                mock_detect,
                mock_ci,
                mock_rebase,
                mock_tasks,
                mock_label,
                mock_pr_info,
            )
        )

        assert "Ready to merge" not in report.recommendations
        assert "Ready to merge (squash-merge safe)" not in report.recommendations

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
    def test_ok_still_yields_ready_to_merge(
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
        mock_linked.return_value = (LinkedBranchStatus.OK, ("255-feature",))

        report = self._collect(
            (
                mock_branch,
                mock_issue_mgr_cls,
                mock_pr_mgr_cls,
                mock_detect,
                mock_ci,
                mock_rebase,
                mock_tasks,
                mock_label,
                mock_pr_info,
            )
        )

        assert "Ready to merge (squash-merge safe)" in report.recommendations
