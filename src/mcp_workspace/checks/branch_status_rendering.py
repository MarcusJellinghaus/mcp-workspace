"""Rendering helpers for :class:`BranchStatusReport`.

Holds the human/LLM formatting functions and the small header helpers
(review gate, wait line) split out of :mod:`branch_status` to keep that
module under the file-size limit. Also defines ``CIStatus``,
``WaitContext`` and ``GITHUB_TOKEN_HINT``, which the rendering logic keys
off of; :mod:`branch_status` re-exports them for backwards compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional

from mcp_workspace.github_operations.ci_log_parser import truncate_ci_details
from mcp_workspace.workflows.task_tracker import TaskTrackerStatus

if TYPE_CHECKING:
    from mcp_workspace.checks.branch_status import BranchStatusReport

GITHUB_TOKEN_HINT = "no GitHub token; set GITHUB_TOKEN or add to config.toml"


class CIStatus(str, Enum):
    """CI pipeline status."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    PENDING = "PENDING"
    UNAVAILABLE = "UNAVAILABLE"  # auth/token missing — CI truth unknown


@dataclass(frozen=True)
class WaitContext:
    """Describes how long the orchestrator waited on CI/PR polling."""

    pr_elapsed: Optional[float] = None
    pr_timeout: int = 0
    ci_elapsed: Optional[float] = None
    ci_timeout: int = 0


def format_report_for_human(
    report: "BranchStatusReport",
    wait_context: Optional[WaitContext] = None,
    fail_on_reviews: bool = False,
) -> str:
    """Format report for human consumption.

    Args:
        report: The branch status report to render.
        wait_context: Optional polling context; renders a ``Wait:`` line
            between ``Base Branch:`` and the report header.
        fail_on_reviews: When True, render a three-state ``Review Gate:``
            header near the top of the report.

    Returns:
        Formatted string with status icons and recommendations.
    """
    # Determine status icons
    ci_icon_map: Dict[CIStatus, str] = {
        CIStatus.UNAVAILABLE: "\U0001f512",
        CIStatus.PASSED: "✅",
        CIStatus.FAILED: "❌",
        CIStatus.PENDING: "⏳",
        CIStatus.NOT_CONFIGURED: "⚙️",
    }
    ci_icon = ci_icon_map.get(report.ci_status, "❓")

    rebase_icon = "✅" if not report.rebase_needed else "⚠️"
    rebase_status_text = "UP TO DATE" if not report.rebase_needed else "BEHIND"

    tasks_icon_map = {
        TaskTrackerStatus.COMPLETE: "✅",
        TaskTrackerStatus.INCOMPLETE: "❌",
        TaskTrackerStatus.ERROR: "⚠️",
    }
    if report.tasks_status == TaskTrackerStatus.N_A:
        tasks_icon = "⚠️" if report.tasks_is_blocking else "➖"
    else:
        tasks_icon = tasks_icon_map.get(report.tasks_status, "❓")
    tasks_status_text = report.tasks_status.value

    # Build the report sections - Branch info first
    lines: List[str] = [
        f"Branch: {report.branch_name}",
        f"Base Branch: {report.base_branch}",
    ]
    wait_line = _format_wait_line(report, wait_context)
    if wait_line is not None:
        lines.append(wait_line)
    lines.extend(
        [
            "",
            "Branch Status Report",
            "",
        ]
    )

    header = _review_gate_header(report, fail_on_reviews)
    if header is not None:
        lines.append(header)

    # PR section (only when pr_found is not None)
    if report.pr_found is not None:
        if report.pr_found:
            lines.append(f"PR: ✅ #{report.pr_number} ({report.pr_url})")
            if report.pr_mergeable is True:
                lines.append("Merge Status: ✅ Mergeable (squash-merge safe)")
            elif report.pr_mergeable is False:
                lines.append("Merge Status: ❌ Not mergeable (has conflicts)")
            else:
                lines.append("Merge Status: ⏳ Pending")
            if report.pr_mergeable_state is not None:
                lines.append(f"Mergeable State: {report.pr_mergeable_state}")
            if report.pr_feedback_text is not None:
                lines.append("")
                lines.append(report.pr_feedback_text)
        else:
            lines.append("PR: ❌ No PR found")
        lines.append("")

    ci_line = f"CI Status: {ci_icon} {report.ci_status.value}"
    if report.ci_status == CIStatus.UNAVAILABLE:
        ci_line += f" — {GITHUB_TOKEN_HINT}"  # em dash
    lines.append(ci_line)

    # Add CI details if they exist
    if report.ci_details:
        lines.extend(
            [
                "",
                "CI Error Details:",
                report.ci_details,
            ]
        )

    lines.extend(
        [
            "",
            f"Rebase Status: {rebase_icon} {rebase_status_text}",
            f"- {report.rebase_reason}",
            "",
            f"Task Tracker: {tasks_icon} {tasks_status_text} ({report.tasks_reason})",
            "",
            f"GitHub Status: {report.current_github_label}",
            "",
            "Recommendations:",
        ]
    )

    # Add recommendations
    for recommendation in report.recommendations:
        lines.append(f"- {recommendation}")

    return "\n".join(lines)


def format_report_for_llm(
    report: "BranchStatusReport",
    max_lines: int = 300,
    wait_context: Optional[WaitContext] = None,
    fail_on_reviews: bool = False,
) -> str:
    """Format report for LLM consumption with truncation.

    Args:
        report: The branch status report to render.
        max_lines: Maximum number of lines for CI error details.
        wait_context: Optional polling context; renders a ``Wait:`` line
            directly below the ``Branch Status:`` summary line.
        fail_on_reviews: When True, render a three-state ``Review Gate:``
            header directly below the status summary line.

    Returns:
        Compact formatted string optimized for LLM context windows.
    """
    # Convert rebase_needed to status string
    rebase_status = "BEHIND" if report.rebase_needed else "UP_TO_DATE"

    # Build status summary line
    status_summary = (
        f"Branch Status: CI={report.ci_status.value}, Rebase={rebase_status}, "
        f"Tasks={report.tasks_status.value} ({report.tasks_reason})"
    )
    if report.ci_status == CIStatus.UNAVAILABLE:
        status_summary += f" ({GITHUB_TOKEN_HINT})"
    if report.pr_found is True:
        mergeable_str = (
            str(report.pr_mergeable) if report.pr_mergeable is not None else "None"
        )
        status_summary += f", PR=#{report.pr_number}, Mergeable={mergeable_str}"
        if report.pr_mergeable_state is not None:
            status_summary += f", Mergeable_State={report.pr_mergeable_state}"
    elif report.pr_found is False:
        status_summary += ", PR=NOT_FOUND"
    recommendations_text = ", ".join(report.recommendations)

    # Branch info on first line
    lines: List[str] = [
        f"Branch: {report.branch_name} | Base: {report.base_branch}",
        status_summary,
    ]
    header = _review_gate_header(report, fail_on_reviews)
    if header is not None:
        lines.append(header)
    wait_line = _format_wait_line(report, wait_context)
    if wait_line is not None:
        lines.append(wait_line)
    lines.extend(
        [
            f"GitHub Label: {report.current_github_label}",
            f"Recommendations: {recommendations_text}",
        ]
    )

    if report.pr_feedback_text is not None:
        lines.append("")
        lines.append(report.pr_feedback_text)

    # Add CI details if they exist, with truncation and footer
    if report.ci_details:
        truncated_details = truncate_ci_details(report.ci_details, max_lines)
        lines.extend(
            [
                "",
                "CI Errors:",
                truncated_details,
                "",
                "---",
                f"Summary: {status_summary} | Action: {recommendations_text}",
            ]
        )

    return "\n".join(lines)


def _review_gate_header(
    report: "BranchStatusReport",
    fail_on_reviews: bool,
) -> Optional[str]:
    """Build the three-state ``Review Gate: ...`` header line.

    Pure function of ``report.ci_status``, ``report.pr_feedback_blocks_merge``,
    and the flag. No token lookup — an ``UNAVAILABLE`` CI status is reused as
    the no-token signal and takes precedence over the blocked/clean states.

    Returns:
        One of the three fixed header strings, or None when the gate is off.
    """
    if not fail_on_reviews:
        return None
    if report.ci_status == CIStatus.UNAVAILABLE:
        return "Review Gate: UNKNOWN (no token)"
    if report.pr_feedback_blocks_merge:
        return "Review Gate: BLOCKED (reviews)"
    return "Review Gate: clean"


def _format_wait_line(
    report: "BranchStatusReport",
    wait_context: Optional[WaitContext],
) -> Optional[str]:
    """Build the ``Wait: ...`` line for the report.

    Returns:
        The formatted ``Wait: ...`` line, or None when nothing to render.
    """
    if wait_context is None:
        return None
    parts: List[str] = []
    if wait_context.ci_timeout > 0 and wait_context.ci_elapsed is not None:
        if report.ci_status == CIStatus.PASSED:
            ci_state = "ok"
        elif report.ci_status == CIStatus.FAILED:
            ci_state = "fail"
        else:
            ci_state = "pending"
        parts.append(f"ci={int(round(wait_context.ci_elapsed))}s {ci_state}")
    if wait_context.pr_timeout > 0 and wait_context.pr_elapsed is not None:
        pr_state = "ok" if report.pr_found else "missing"
        parts.append(f"pr={int(round(wait_context.pr_elapsed))}s {pr_state}")
    if not parts:
        return None
    return f"Wait: {', '.join(parts)}"
