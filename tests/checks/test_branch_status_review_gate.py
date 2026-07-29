"""Tests for the review-gate header and missing-token (UNAVAILABLE) rendering."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp_workspace.checks.branch_status import (
    BranchStatusReport,
    _collect_ci_status,
    _generate_recommendations,
    collect_branch_status,
)
from mcp_workspace.checks.branch_status_rendering import (
    GITHUB_TOKEN_HINT,
    CIStatus,
    _review_gate_header,
)
from mcp_workspace.workflows.task_tracker import TaskTrackerStatus


def _make_report(ci_status: CIStatus) -> BranchStatusReport:
    """Build a minimal report with the given CI status for rendering tests."""
    return BranchStatusReport(
        branch_name="123-feature",
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
    )


class TestUnavailableCIStatus:
    """Tests for the missing-token CI degradation (UNAVAILABLE)."""

    def test_ci_status_enum_has_unavailable(self) -> None:
        assert CIStatus.UNAVAILABLE == "UNAVAILABLE"
        assert CIStatus.UNAVAILABLE.value == "UNAVAILABLE"

    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    @patch(
        "mcp_workspace.checks.branch_status.get_github_token",
        return_value=None,
    )
    def test_collect_ci_status_no_token_returns_unavailable(
        self, _mock_token: MagicMock, mock_ci_cls: MagicMock
    ) -> None:
        """Missing token short-circuits before any manager construction."""
        result = _collect_ci_status(Path("/tmp"), "main", 300)
        assert result == (CIStatus.UNAVAILABLE, None, [])
        mock_ci_cls.assert_not_called()

    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    @patch(
        "mcp_workspace.checks.branch_status.get_github_token",
        return_value="tok",
    )
    def test_collect_ci_status_with_token_still_works(
        self, _mock_token: MagicMock, mock_ci_cls: MagicMock
    ) -> None:
        """With a token present the CI-manager path is still exercised."""
        mock_ci = MagicMock()
        mock_ci.get_latest_ci_status.return_value = {
            "run": {"conclusion": "success", "status": "completed"},
            "jobs": [],
        }
        mock_ci_cls.return_value = mock_ci
        status, details, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.PASSED
        assert details is None
        assert failing_names == []
        mock_ci_cls.assert_called_once()

    def test_format_for_human_unavailable_status(self) -> None:
        report = _make_report(CIStatus.UNAVAILABLE)
        output = report.format_for_human()
        assert f"CI Status: \U0001f512 UNAVAILABLE — {GITHUB_TOKEN_HINT}" in output

    def test_format_for_llm_unavailable_status(self) -> None:
        report = _make_report(CIStatus.UNAVAILABLE)
        output = report.format_for_llm()
        summary_line = output.splitlines()[1]
        assert "CI=UNAVAILABLE" in summary_line
        assert f"({GITHUB_TOKEN_HINT})" in summary_line

    def test_recommendations_unavailable_includes_token_hint(self) -> None:
        recommendations = _generate_recommendations(
            {
                "ci_status": CIStatus.UNAVAILABLE,
                "tasks_status": TaskTrackerStatus.N_A,
                "tasks_is_blocking": False,
            }
        )
        assert f"Set a GitHub token ({GITHUB_TOKEN_HINT})" in recommendations
        assert "Configure CI pipeline" not in recommendations
        assert "Ready to merge" not in recommendations


def _make_gate_report(
    ci_status: CIStatus,
    pr_feedback_blocks_merge: bool,
    pr_feedback_undeterminable: bool = False,
) -> BranchStatusReport:
    """Build a report for review-gate rendering tests."""
    return replace(
        _make_report(ci_status),
        pr_feedback_blocks_merge=pr_feedback_blocks_merge,
        pr_feedback_undeterminable=pr_feedback_undeterminable,
    )


class TestReviewGateHeader:
    """Tests for the opt-in three-state review-gate header."""

    def test_review_gate_absent_when_off(self) -> None:
        """Default (fail_on_reviews=False): no gate line in either formatter."""
        report = _make_gate_report(CIStatus.PASSED, pr_feedback_blocks_merge=True)
        assert "Review Gate:" not in report.format_for_human()
        assert "Review Gate:" not in report.format_for_llm()

    def test_review_gate_blocked(self) -> None:
        report = _make_gate_report(CIStatus.PASSED, pr_feedback_blocks_merge=True)
        assert "Review Gate: BLOCKED (reviews)" in report.format_for_human(
            fail_on_reviews=True
        )
        assert "Review Gate: BLOCKED (reviews)" in report.format_for_llm(
            fail_on_reviews=True
        )

    def test_review_gate_clean(self) -> None:
        report = _make_gate_report(CIStatus.PASSED, pr_feedback_blocks_merge=False)
        assert "Review Gate: clean" in report.format_for_human(fail_on_reviews=True)
        assert "Review Gate: clean" in report.format_for_llm(fail_on_reviews=True)

    def test_review_gate_unknown_no_token(self) -> None:
        report = _make_gate_report(CIStatus.UNAVAILABLE, pr_feedback_blocks_merge=False)
        for output in (
            report.format_for_human(fail_on_reviews=True),
            report.format_for_llm(fail_on_reviews=True),
        ):
            assert "Review Gate: UNKNOWN (no token)" in output
            assert "Review Gate: clean" not in output
            assert "Review Gate: BLOCKED" not in output

    def test_review_gate_unknown_wins_over_blocks(self) -> None:
        report = _make_gate_report(CIStatus.UNAVAILABLE, pr_feedback_blocks_merge=True)
        for output in (
            report.format_for_human(fail_on_reviews=True),
            report.format_for_llm(fail_on_reviews=True),
        ):
            assert "Review Gate: UNKNOWN (no token)" in output
            assert "Review Gate: BLOCKED" not in output

    def test_review_gate_helper_returns_none_when_off(self) -> None:
        report = _make_gate_report(CIStatus.PASSED, pr_feedback_blocks_merge=True)
        assert _review_gate_header(report, False) is None

    def test_ci_unknown_token_present_renders_undeterminable(self) -> None:
        """CI UNKNOWN (collection failure, token may be present) → undeterminable."""
        report = _make_gate_report(CIStatus.UNKNOWN, pr_feedback_blocks_merge=False)
        for output in (
            report.format_for_human(fail_on_reviews=True),
            report.format_for_llm(fail_on_reviews=True),
        ):
            assert "Review Gate: UNKNOWN (undeterminable)" in output
            assert "Review Gate: UNKNOWN (no token)" not in output
            assert "Review Gate: clean" not in output

    def test_pr_feedback_undeterminable_threads_renders_unknown(self) -> None:
        """Token present + CI PASSED + blocking review data unavailable → UNKNOWN.

        Simulates the partial-degradation fail-open: blocks_merge is False
        because the threads section was unavailable, not because it was clean.
        """
        report = _make_gate_report(
            CIStatus.PASSED,
            pr_feedback_blocks_merge=False,
            pr_feedback_undeterminable=True,
        )
        for output in (
            report.format_for_human(fail_on_reviews=True),
            report.format_for_llm(fail_on_reviews=True),
        ):
            assert "Review Gate: UNKNOWN (undeterminable)" in output
            assert "Review Gate: UNKNOWN (no token)" not in output
            assert "Review Gate: clean" not in output

    def test_pr_feedback_undeterminable_wins_over_clean(self) -> None:
        """The helper is a pure function; undeterminable overrides clean."""
        report = _make_gate_report(
            CIStatus.PASSED,
            pr_feedback_blocks_merge=False,
            pr_feedback_undeterminable=True,
        )
        assert (
            _review_gate_header(report, True) == "Review Gate: UNKNOWN (undeterminable)"
        )

    def test_pr_feedback_undeterminable_off_is_pure_additive(self) -> None:
        """fail_on_reviews OFF: output byte-for-byte unchanged by the new field."""
        determinable = _make_gate_report(
            CIStatus.PASSED,
            pr_feedback_blocks_merge=False,
            pr_feedback_undeterminable=False,
        )
        undeterminable = _make_gate_report(
            CIStatus.PASSED,
            pr_feedback_blocks_merge=False,
            pr_feedback_undeterminable=True,
        )
        assert determinable.format_for_human() == undeterminable.format_for_human()
        assert determinable.format_for_llm() == undeterminable.format_for_llm()
        assert "Review Gate:" not in undeterminable.format_for_human()

    def test_review_gate_collection_failure_is_unknown_not_clean(self) -> None:
        """A status-collection failure must not fail open to 'clean'.

        The catch-all handler in collect_branch_status returns an empty report
        on any exception; with the gate on it must render UNKNOWN, since the
        review state was never determined. A token may be present, so the
        cause reads ``(undeterminable)`` rather than ``(no token)``.
        """
        with patch(
            "mcp_workspace.checks.branch_status.get_current_branch_name",
            side_effect=RuntimeError("boom"),
        ):
            report = collect_branch_status(Path("/tmp"))

        assert report.ci_status == CIStatus.UNKNOWN
        for output in (
            report.format_for_human(fail_on_reviews=True),
            report.format_for_llm(fail_on_reviews=True),
        ):
            assert "Review Gate: UNKNOWN (undeterminable)" in output
            assert "Review Gate: clean" not in output
            assert "Review Gate: BLOCKED" not in output

    @patch(
        "mcp_workspace.checks.branch_status.get_github_token",
        return_value="tok",
    )
    def test_undeterminable_paths_do_not_misattribute_missing_token(
        self, _mock_token: MagicMock
    ) -> None:
        """Undeterminable paths must not blame a missing token when one is present.

        With a token available, both the branch-undeterminable path and the
        generic collection-failure path must yield the review-gate UNKNOWN
        verdict while rendering a neutral (UNKNOWN, not UNAVAILABLE) CI cause
        and omitting the GITHUB_TOKEN_HINT from the CI line and recommendations.
        """
        branch_none = patch(
            "mcp_workspace.checks.branch_status.get_current_branch_name",
            return_value=None,
        )
        collection_fails = patch(
            "mcp_workspace.checks.branch_status.get_current_branch_name",
            side_effect=RuntimeError("boom"),
        )
        for path_patch in (branch_none, collection_fails):
            with path_patch:
                report = collect_branch_status(Path("/tmp"))

            assert report.ci_status == CIStatus.UNKNOWN
            human = report.format_for_human(fail_on_reviews=True)
            llm = report.format_for_llm(fail_on_reviews=True)
            for output in (human, llm):
                # Review-gate verdict is still UNKNOWN (undeterminable) — a
                # token is present, so the cause must not read "(no token)".
                assert "Review Gate: UNKNOWN (undeterminable)" in output
                assert "Review Gate: UNKNOWN (no token)" not in output
                assert "Review Gate: clean" not in output
                assert "Review Gate: BLOCKED" not in output
                # ...but the CI cause must not blame a token that is present.
                assert GITHUB_TOKEN_HINT not in output
                assert "UNAVAILABLE" not in output
            assert "CI Status: ❓ UNKNOWN" in human
            assert "CI=UNKNOWN" in llm
