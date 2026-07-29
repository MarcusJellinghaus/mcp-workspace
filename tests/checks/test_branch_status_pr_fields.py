"""Tests for BranchStatusReport PR-related fields."""

from mcp_workspace.checks.branch_status import BranchStatusReport
from mcp_workspace.checks.branch_status_rendering import CIStatus
from mcp_workspace.workflows.task_tracker import TaskTrackerStatus


def _make_report(
    pr_number: int | None = None,
    pr_url: str | None = None,
    pr_found: bool | None = None,
    pr_mergeable: bool | None = None,
    pr_mergeable_state: str | None = None,
    pr_feedback_text: str | None = None,
    pr_feedback_blocks_merge: bool = False,
) -> BranchStatusReport:
    """Helper to create a report with specific PR fields."""
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
        current_github_label="",
        recommendations=[],
        pr_number=pr_number,
        pr_url=pr_url,
        pr_found=pr_found,
        pr_mergeable=pr_mergeable,
        pr_mergeable_state=pr_mergeable_state,
        pr_feedback_text=pr_feedback_text,
        pr_feedback_blocks_merge=pr_feedback_blocks_merge,
    )


class TestPRFieldDefaults:
    """Tests that PR fields default to None."""

    def test_defaults_are_none(self) -> None:
        report = _make_report()
        assert report.pr_number is None
        assert report.pr_url is None
        assert report.pr_found is None


class TestPRFieldsInHumanFormat:
    """Tests PR field rendering in human format."""

    def test_pr_found_shows_in_output(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
        )
        output = report.format_for_human()
        assert "PR:" in output
        assert "#42" in output

    def test_pr_not_found_shows_no_pr(self) -> None:
        report = _make_report(pr_found=False)
        output = report.format_for_human()
        assert "No PR found" in output

    def test_pr_none_hides_pr_line(self) -> None:
        report = _make_report(pr_found=None)
        output = report.format_for_human()
        assert "PR:" not in output


class TestPRFieldsInLLMFormat:
    """Tests PR field rendering in LLM format."""

    def test_pr_found_shows_in_output(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
        )
        output = report.format_for_llm()
        assert "PR=#42" in output

    def test_pr_not_found_shows_no_pr(self) -> None:
        report = _make_report(pr_found=False)
        output = report.format_for_llm()
        assert "PR=NOT_FOUND" in output

    def test_pr_none_hides_pr_section(self) -> None:
        report = _make_report(pr_found=None)
        output = report.format_for_llm()
        assert "PR=" not in output


class TestMergeStatusInHumanFormat:
    """Tests Merge Status line rendering in human format."""

    def test_mergeable_true(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=True,
        )
        output = report.format_for_human()
        assert "Mergeable (squash-merge safe)" in output

    def test_mergeable_false(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=False,
        )
        output = report.format_for_human()
        assert "Not mergeable (has conflicts)" in output

    def test_mergeable_none(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=None,
        )
        output = report.format_for_human()
        assert "Pending" in output

    def test_no_pr_omits_merge_status(self) -> None:
        report = _make_report(pr_found=False)
        output = report.format_for_human()
        assert "Merge Status" not in output

    def test_pr_none_omits_merge_status(self) -> None:
        report = _make_report(pr_found=None)
        output = report.format_for_human()
        assert "Merge Status" not in output


class TestMergeStatusInLLMFormat:
    """Tests Mergeable= token rendering in LLM format."""

    def test_mergeable_true(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=True,
        )
        output = report.format_for_llm()
        assert "Mergeable=True" in output

    def test_mergeable_false(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=False,
        )
        output = report.format_for_llm()
        assert "Mergeable=False" in output

    def test_mergeable_none(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=None,
        )
        output = report.format_for_llm()
        assert "Mergeable=None" in output

    def test_no_pr_omits_mergeable(self) -> None:
        report = _make_report(pr_found=False)
        output = report.format_for_llm()
        assert "Mergeable=" not in output


class TestMergeableStateRendering:
    """Tests for `pr_mergeable_state` rendering in both formatters."""

    def test_mergeable_state_in_human_format(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=True,
            pr_mergeable_state="clean",
        )
        output = report.format_for_human()
        assert "clean" in output

    def test_mergeable_state_in_llm_format(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=True,
            pr_mergeable_state="clean",
        )
        output = report.format_for_llm()
        assert "Mergeable_State=clean" in output

    def test_mergeable_state_none_omitted_in_llm_format(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=True,
            pr_mergeable_state=None,
        )
        output = report.format_for_llm()
        assert "Mergeable_State" not in output


class TestPRFeedbackTextRendering:
    """Tests for `pr_feedback_text` rendering in both formatters."""

    def test_pr_feedback_text_in_human_format(self) -> None:
        feedback_text = (
            "PR Reviews:\n[alert] py/sql-injection: SQL injection @ src/db.py:17"
        )
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=True,
            pr_feedback_text=feedback_text,
        )
        output = report.format_for_human()
        assert feedback_text in output

    def test_pr_feedback_text_in_llm_format(self) -> None:
        feedback_text = (
            "PR Reviews:\n[alert] py/sql-injection: SQL injection @ src/db.py:17"
        )
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=True,
            pr_feedback_text=feedback_text,
        )
        output = report.format_for_llm()
        assert feedback_text in output

    def test_pr_feedback_text_none_omits_block_in_human(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=True,
            pr_feedback_text=None,
        )
        output = report.format_for_human()
        assert "PR Reviews:" not in output

    def test_pr_feedback_text_none_omits_block_in_llm(self) -> None:
        report = _make_report(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_found=True,
            pr_mergeable=True,
            pr_feedback_text=None,
        )
        output = report.format_for_llm()
        assert "PR Reviews:" not in output
