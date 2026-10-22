"""Tests for base-branch handling in branch status: tri-state rebase, rebase target."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.checks.branch_status import (
    BranchStatusReport,
    _apply_pr_merge_override,
    _generate_recommendations,
    collect_branch_status,
)
from mcp_workspace.checks.branch_status_rendering import CIStatus, LinkedBranchStatus
from mcp_workspace.github_operations.issues.base import (
    MalformedBaseBranchError,
    format_malformed_base_branch,
    parse_base_branch,
)
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


_MALFORMED_BODY = "### Base Branch\n\nepic/x\nmore\n"
_ERROR_SENTENCE = "Base Branch section spans multiple lines"
_MALFORMED_BASE = "MALFORMED (issue #42: 'epic/x')"


@pytest.fixture(name="status_mocks")
def _status_mocks() -> Iterator[dict[str, MagicMock]]:
    """Patch every collector ``collect_branch_status`` reaches out to."""
    prefix = "mcp_workspace.checks.branch_status"
    targets = {
        "branch": "get_current_branch_name",
        "issue_mgr_cls": "IssueManager",
        "pr_mgr_cls": "PullRequestManager",
        "detect": "detect_base_branch",
        "needs_rebase": "needs_rebase",
        "ci": "_collect_ci_status",
        "linked": "_collect_linked_branch_status",
        "tasks": "_collect_task_status",
        "pr_info": "_collect_pr_info",
        "default": "get_default_branch_name",
    }
    patchers = {key: patch(f"{prefix}.{name}") for key, name in targets.items()}
    mocks = {key: p.start() for key, p in patchers.items()}
    mocks["branch"].return_value = "42-feature"
    mocks["issue_mgr_cls"].return_value.get_comments.return_value = []
    mocks["detect"].return_value = "main"
    mocks["needs_rebase"].return_value = (False, "up to date")
    mocks["ci"].return_value = (CIStatus.PASSED, None, [])
    mocks["linked"].return_value = (LinkedBranchStatus.OK, ("42-feature",), 42, None)
    mocks["tasks"].return_value = (TaskTrackerStatus.COMPLETE, "All done", False)
    mocks["pr_info"].return_value = (None, None, False, None, None)
    mocks["default"].return_value = "main"
    yield mocks
    for p in patchers.values():
        p.stop()


def _set_issue(mocks: dict[str, MagicMock], issue: dict[str, Any]) -> None:
    mocks["issue_mgr_cls"].return_value.get_issue.return_value = issue


class TestMalformedBaseBranch:
    """A malformed Base Branch is surfaced, never replaced by a guessed base."""

    @pytest.fixture(name="report")
    def _report(self, status_mocks: dict[str, MagicMock]) -> BranchStatusReport:
        _set_issue(
            status_mocks,
            {
                "number": 42,
                "body": _MALFORMED_BODY,
                "base_branch": None,
                "base_branch_error": _ERROR_SENTENCE,
            },
        )
        return collect_branch_status(Path("/tmp"))

    def test_skips_detection_and_rebase(
        self, report: BranchStatusReport, status_mocks: dict[str, MagicMock]
    ) -> None:
        assert report.base_branch == _MALFORMED_BASE
        status_mocks["detect"].assert_not_called()
        status_mocks["needs_rebase"].assert_not_called()

    def test_report_fields(self, report: BranchStatusReport) -> None:
        assert report.base_branch == _MALFORMED_BASE
        assert report.base_branch_error == _ERROR_SENTENCE
        assert report.rebase_needed is None
        assert report.rebase_reason == "base branch malformed in issue #42"

    def test_recommendations(self, report: BranchStatusReport) -> None:
        recs = report.recommendations
        assert "Fix the ### Base Branch section in issue #42" in recs
        assert not any(r.startswith("Ready to merge") for r in recs)
        assert not any(r.startswith("Rebase onto") for r in recs)
        assert not any(r.startswith("Pull ") for r in recs)

    def test_llm_output(self, report: BranchStatusReport) -> None:
        output = report.format_for_llm(fail_on_reviews=True)
        assert f"Base: {_MALFORMED_BASE}" in output
        assert "Rebase=UNKNOWN" in output
        assert "Review Gate: BLOCKED (base branch)" in output

    def test_human_output(self, report: BranchStatusReport) -> None:
        output = report.format_for_human(fail_on_reviews=True)
        assert f"Base Branch: {_MALFORMED_BASE}" in output
        assert "Rebase Status: ❓ UNKNOWN" in output
        assert "- base branch malformed in issue #42" in output
        assert "Review Gate: BLOCKED (base branch)" in output


class TestInvalidRefBaseBranch:
    """A single-line but invalid ref is surfaced as MALFORMED with its value."""

    def test_malformed_line_shows_value(
        self, status_mocks: dict[str, MagicMock]
    ) -> None:
        body = "### Base Branch\n\nmain branch\n"
        with pytest.raises(MalformedBaseBranchError) as exc_info:
            parse_base_branch(body)
        _set_issue(
            status_mocks,
            {
                "number": 42,
                "body": body,
                "base_branch": None,
                "base_branch_error": format_malformed_base_branch(exc_info.value),
            },
        )

        report = collect_branch_status(Path("/tmp"))

        assert report.base_branch == "MALFORMED (issue #42: 'main branch')"
        status_mocks["detect"].assert_not_called()


class TestValidBaseBranch:
    """A valid issue goes through base-branch detection with the fetched data."""

    def test_detect_called_with_fetched_issue(
        self, status_mocks: dict[str, MagicMock]
    ) -> None:
        issue = {
            "number": 42,
            "body": "### Base Branch\n\nepic/x\n",
            "base_branch": "epic/x",
            "base_branch_error": None,
        }
        _set_issue(status_mocks, issue)
        status_mocks["detect"].return_value = "epic/x"

        report = collect_branch_status(Path("/tmp"))

        status_mocks["detect"].assert_called_once()
        kwargs = status_mocks["detect"].call_args.kwargs
        assert kwargs["issue_data"] == issue
        assert "issue_manager" not in kwargs
        assert report.base_branch == "epic/x"
        assert report.base_branch_error is None
        assert report.rebase_needed is False
