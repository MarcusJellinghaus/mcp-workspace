"""Tests for base-branch handling in branch status: tri-state rebase, rebase target."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp_workspace.checks.branch_status import (
    BranchStatusReport,
    _apply_pr_merge_override,
    _generate_recommendations,
    collect_branch_status,
)
from mcp_workspace.checks.branch_status_rendering import CIStatus, LinkedBranchStatus
from mcp_workspace.workflows.task_tracker import TaskTrackerStatus


def _make_report(rebase_needed: bool | None) -> BranchStatusReport:
    return BranchStatusReport(
        branch_name="123-feature",
        base_branch="main",
        ci_status=CIStatus.PASSED,
        ci_details=None,
        rebase_needed=rebase_needed,
        rebase_reason="rebase check skipped",
        tasks_status=TaskTrackerStatus.COMPLETE,
        tasks_reason="All 5 tasks complete",
        tasks_is_blocking=False,
        current_github_label="status-04:in-progress",
        recommendations=[],
    )


class TestRebaseRecommendationTarget:
    """The rebase recommendation names the detected base branch."""

    def test_names_detected_base_not_default(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": True,
                "base_branch": "epic/x",
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "is_default_branch": False,
                "default_branch_name": "main",
            }
        )
        assert "Rebase onto origin/epic/x" in recs
        assert "Rebase onto origin/main" not in recs

    @patch("mcp_workspace.checks.branch_status.get_default_branch_name")
    @patch("mcp_workspace.checks.branch_status._collect_pr_info")
    @patch("mcp_workspace.checks.branch_status._collect_task_status")
    @patch("mcp_workspace.checks.branch_status.needs_rebase")
    @patch("mcp_workspace.checks.branch_status._collect_ci_status")
    @patch("mcp_workspace.checks.branch_status.detect_base_branch")
    @patch("mcp_workspace.checks.branch_status.PullRequestManager")
    @patch("mcp_workspace.checks.branch_status.IssueManager")
    @patch("mcp_workspace.checks.branch_status.get_current_branch_name")
    @patch(
        "mcp_workspace.checks.branch_status._collect_linked_branch_status",
        return_value=(LinkedBranchStatus.OK, ("123-feature",), 123, None),
    )
    def test_undetected_base_falls_back_to_default(
        self,
        _mock_linked: MagicMock,
        mock_branch: MagicMock,
        mock_issue_mgr_cls: MagicMock,
        mock_pr_mgr_cls: MagicMock,
        mock_detect: MagicMock,
        mock_ci: MagicMock,
        mock_needs_rebase: MagicMock,
        mock_tasks: MagicMock,
        mock_pr_info: MagicMock,
        mock_default: MagicMock,
    ) -> None:
        mock_branch.return_value = "123-feature"
        mock_issue_mgr_cls.return_value.get_issue.return_value = {"number": 123}
        mock_issue_mgr_cls.return_value.get_comments.return_value = []
        mock_pr_mgr_cls.return_value = MagicMock()
        mock_detect.return_value = None
        mock_ci.return_value = (CIStatus.PASSED, None, [])
        mock_needs_rebase.return_value = (True, "3 commits behind")
        mock_tasks.return_value = (TaskTrackerStatus.COMPLETE, "All done", False)
        mock_pr_info.return_value = (None, None, False, None, None)
        mock_default.return_value = "main"

        report = collect_branch_status(Path("/tmp"))

        assert "Rebase onto origin/main" in report.recommendations
        assert not any("origin/unknown" in r for r in report.recommendations)


class TestUnknownRebaseState:
    """``rebase_needed=None`` means UNKNOWN: no rebase action, no merge verdict."""

    def test_no_rebase_pull_or_ready_recommendation(self) -> None:
        for is_default_branch in (False, True):
            recs = _generate_recommendations(
                {
                    "ci_status": CIStatus.PASSED,
                    "rebase_needed": None,
                    "base_branch": "main",
                    "tasks_status": TaskTrackerStatus.COMPLETE,
                    "tasks_reason": "All done",
                    "tasks_is_blocking": False,
                    "is_default_branch": is_default_branch,
                    "default_branch_name": "main",
                }
            )
            assert not any(r.startswith("Rebase onto") for r in recs)
            assert not any(r.startswith("Pull ") for r in recs)
            assert not any(r.startswith("Ready to merge") for r in recs)

    def test_merge_override_passes_none_through(self) -> None:
        assert _apply_pr_merge_override(None, "r", True) == (None, "r")

    def test_llm_renders_unknown(self) -> None:
        output = _make_report(None).format_for_llm()
        assert "Rebase=UNKNOWN" in output

    def test_human_renders_unknown(self) -> None:
        output = _make_report(None).format_for_human()
        assert "Rebase Status: ❓ UNKNOWN" in output

    def test_renderers_keep_known_states(self) -> None:
        assert "Rebase=BEHIND" in _make_report(True).format_for_llm()
        assert "Rebase=UP_TO_DATE" in _make_report(False).format_for_llm()
        assert "Rebase Status: ⚠️ BEHIND" in _make_report(True).format_for_human()
        assert "Rebase Status: ✅ UP TO DATE" in _make_report(False).format_for_human()
