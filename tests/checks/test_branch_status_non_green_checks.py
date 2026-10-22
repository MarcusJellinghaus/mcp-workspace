"""Tests for the ``Non-green checks:`` line and ``format_check_names``."""

from typing import Optional

import pytest

from mcp_workspace.checks.branch_status import BranchStatusReport
from mcp_workspace.checks.branch_status_rendering import (
    MAX_CHECK_NAMES,
    CIStatus,
    WaitContext,
    format_check_names,
)
from mcp_workspace.workflows.task_tracker import TaskTrackerStatus

_REASON = "token lacks permission (Checks: read / Commit statuses: read)"


def _make_report(
    non_green_checks: Optional[tuple[str, ...]] = None,
    non_green_checks_error: Optional[str] = None,
) -> BranchStatusReport:
    """Build a report with an ``unstable`` PR and the given lookup result."""
    return BranchStatusReport(
        branch_name="test-branch",
        base_branch="main",
        ci_status=CIStatus.PASSED,
        ci_details=None,
        rebase_needed=False,
        rebase_reason="up-to-date",
        tasks_status=TaskTrackerStatus.COMPLETE,
        tasks_reason="All done",
        tasks_is_blocking=False,
        current_github_label="status-07:code-review",
        recommendations=[],
        pr_number=42,
        pr_url="https://github.com/owner/repo/pull/42",
        pr_found=True,
        pr_mergeable=True,
        pr_mergeable_state="unstable",
        non_green_checks=non_green_checks,
        non_green_checks_error=non_green_checks_error,
    )


def _line_index(lines: list[str], prefix: str) -> int:
    [index] = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    return index


class TestNonGreenChecksHuman:
    """``Non-green checks:`` line in the human format."""

    def test_names_line_follows_mergeable_state(self) -> None:
        report = _make_report(non_green_checks=("codecov/patch (pending)",))
        lines = report.format_for_human().splitlines()
        idx = _line_index(lines, "Non-green checks:")
        assert lines[idx] == "Non-green checks: codecov/patch (pending)"
        assert lines[idx - 1] == "Mergeable State: unstable"

    def test_error_line(self) -> None:
        report = _make_report(non_green_checks=(), non_green_checks_error=_REASON)
        output = report.format_for_human()
        assert f"Non-green checks: lookup failed — {_REASON}" in output

    @pytest.mark.parametrize("names", [None, ()])
    def test_no_line_without_names_or_error(
        self, names: Optional[tuple[str, ...]]
    ) -> None:
        report = _make_report(non_green_checks=names)
        assert "Non-green checks:" not in report.format_for_human()

    def test_twelve_names_capped(self) -> None:
        names = tuple(f"check-{i:02d}" for i in range(1, 13))
        report = _make_report(non_green_checks=names)
        lines = report.format_for_human().splitlines()
        line = lines[_line_index(lines, "Non-green checks:")]
        assert line == f"Non-green checks: {', '.join(names[:10])}, … and 2 more"


class TestNonGreenChecksLlm:
    """``Non-green checks:`` line in the LLM format."""

    def test_names_line_before_github_label(self) -> None:
        report = _make_report(non_green_checks=("codecov/patch (pending)",))
        lines = report.format_for_llm().splitlines()
        idx = _line_index(lines, "Non-green checks:")
        assert lines[idx] == "Non-green checks: codecov/patch (pending)"
        assert lines[idx + 1].startswith("GitHub Label:")
        status_line = lines[_line_index(lines, "Branch Status:")]
        assert "Non-green" not in status_line
        assert "codecov" not in status_line

    def test_names_line_after_wait_line(self) -> None:
        report = _make_report(non_green_checks=("codecov/patch (pending)",))
        output = report.format_for_llm(
            wait_context=WaitContext(ci_elapsed=41, ci_timeout=60)
        )
        lines = output.splitlines()
        wait_idx = _line_index(lines, "Wait:")
        idx = _line_index(lines, "Non-green checks:")
        assert wait_idx < idx < _line_index(lines, "GitHub Label:")

    def test_error_line(self) -> None:
        report = _make_report(non_green_checks=(), non_green_checks_error=_REASON)
        output = report.format_for_llm()
        assert f"Non-green checks: lookup failed — {_REASON}" in output

    @pytest.mark.parametrize("names", [None, ()])
    def test_no_line_without_names_or_error(
        self, names: Optional[tuple[str, ...]]
    ) -> None:
        report = _make_report(non_green_checks=names)
        assert "Non-green checks:" not in report.format_for_llm()

    def test_twelve_names_capped(self) -> None:
        names = tuple(f"check-{i:02d}" for i in range(1, 13))
        report = _make_report(non_green_checks=names)
        lines = report.format_for_llm().splitlines()
        line = lines[_line_index(lines, "Non-green checks:")]
        assert line == f"Non-green checks: {', '.join(names[:10])}, … and 2 more"


class TestFormatCheckNames:
    """Tests for ``format_check_names``."""

    def test_exactly_max_names_has_no_suffix(self) -> None:
        names = [f"check-{i:02d}" for i in range(1, MAX_CHECK_NAMES + 1)]
        assert format_check_names(names) == ", ".join(names)

    def test_over_max_adds_suffix(self) -> None:
        names = [f"check-{i:02d}" for i in range(1, MAX_CHECK_NAMES + 3)]
        result = format_check_names(names)
        assert result == f"{', '.join(names[:MAX_CHECK_NAMES])}, … and 2 more"
