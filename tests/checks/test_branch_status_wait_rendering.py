"""Unit tests for ``WaitContext`` rendering on report formatters."""

from typing import Optional

from mcp_workspace.checks.branch_status import (
    BranchStatusReport,
    CIStatus,
    WaitContext,
)
from mcp_workspace.workflows.task_tracker import TaskTrackerStatus


class TestWaitLineRendering:
    """Tests for ``WaitContext`` rendering on both formatters."""

    @staticmethod
    def _make_report(
        *,
        ci_status: CIStatus = CIStatus.PASSED,
        pr_found: Optional[bool] = None,
    ) -> BranchStatusReport:
        return BranchStatusReport(
            branch_name="feature/x",
            base_branch="main",
            ci_status=ci_status,
            ci_details=None,
            rebase_needed=False,
            rebase_reason="up to date",
            tasks_status=TaskTrackerStatus.COMPLETE,
            tasks_reason="all done",
            tasks_is_blocking=False,
            current_github_label="status-ready",
            recommendations=["Ready to merge"],
            pr_found=pr_found,
        )

    def test_wait_line_both_sides_ci_ok_pr_missing(self) -> None:
        report = self._make_report(ci_status=CIStatus.PASSED, pr_found=False)
        ctx = WaitContext(
            ci_elapsed=80.0,
            ci_timeout=300,
            pr_elapsed=300.0,
            pr_timeout=300,
        )
        rendered = report.format_for_llm(wait_context=ctx)
        assert "Wait: ci=80s ok, pr=300s missing" in rendered

    def test_wait_line_ci_fail_pr_ok(self) -> None:
        report = self._make_report(ci_status=CIStatus.FAILED, pr_found=True)
        ctx = WaitContext(
            ci_elapsed=42.0,
            ci_timeout=300,
            pr_elapsed=10.0,
            pr_timeout=300,
        )
        rendered = report.format_for_llm(wait_context=ctx)
        assert "Wait: ci=42s fail, pr=10s ok" in rendered

    def test_wait_line_ci_pending_when_status_not_configured(self) -> None:
        report = self._make_report(ci_status=CIStatus.NOT_CONFIGURED)
        ctx = WaitContext(ci_elapsed=15.0, ci_timeout=60)
        rendered = report.format_for_llm(wait_context=ctx)
        assert "ci=15s pending" in rendered

    def test_wait_line_omits_ci_side_when_ci_timeout_zero(self) -> None:
        report = self._make_report(pr_found=True)
        ctx = WaitContext(
            ci_elapsed=None,
            ci_timeout=0,
            pr_elapsed=10.0,
            pr_timeout=120,
        )
        rendered = report.format_for_llm(wait_context=ctx)
        assert "Wait: pr=10s ok" in rendered
        assert "ci=" not in rendered

    def test_wait_line_omits_pr_side_when_pr_timeout_zero(self) -> None:
        report = self._make_report(ci_status=CIStatus.PASSED)
        ctx = WaitContext(
            ci_elapsed=20.0,
            ci_timeout=120,
            pr_elapsed=None,
            pr_timeout=0,
        )
        rendered = report.format_for_llm(wait_context=ctx)
        assert "Wait: ci=20s ok" in rendered
        assert "pr=" not in rendered

    def test_wait_line_absent_when_both_timeouts_zero(self) -> None:
        report = self._make_report()
        ctx = WaitContext()
        rendered = report.format_for_llm(wait_context=ctx)
        assert "Wait:" not in rendered

    def test_wait_line_absent_when_no_wait_context(self) -> None:
        report = self._make_report()
        with_default = report.format_for_llm()
        with_none = report.format_for_llm(wait_context=None)
        assert "Wait:" not in with_default
        assert with_default == with_none

    def test_format_for_human_unchanged_when_no_wait_context(self) -> None:
        report = self._make_report()
        with_default = report.format_for_human()
        with_none = report.format_for_human(wait_context=None)
        assert "Wait:" not in with_default
        assert with_default == with_none

    def test_format_for_human_renders_same_wait_line(self) -> None:
        report = self._make_report(ci_status=CIStatus.PASSED)
        ctx = WaitContext(ci_elapsed=10.0, ci_timeout=60)
        rendered = report.format_for_human(wait_context=ctx)
        assert "Wait: ci=10s ok" in rendered

        lines = rendered.split("\n")
        base_idx = next(
            i for i, ln in enumerate(lines) if ln.startswith("Base Branch:")
        )
        wait_idx = next(i for i, ln in enumerate(lines) if ln.startswith("Wait:"))
        report_idx = next(
            i for i, ln in enumerate(lines) if ln == "Branch Status Report"
        )
        assert wait_idx == base_idx + 1
        assert lines[wait_idx + 1] == ""
        assert report_idx == wait_idx + 2
