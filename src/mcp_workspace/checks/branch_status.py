"""Branch status check — comprehensive branch readiness report.

Collects CI status, rebase status, task tracker progress, and GitHub
labels into a single BranchStatusReport dataclass. Used by the
check_branch_status MCP tool.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from mcp_workspace.checks.pr_feedback import collect_pr_feedback
from mcp_workspace.git_operations.base_branch import detect_base_branch
from mcp_workspace.git_operations.branch_queries import (
    extract_issue_number_from_branch,
    get_current_branch_name,
)
from mcp_workspace.git_operations.workflows import needs_rebase
from mcp_workspace.github_operations.ci_log_parser import (
    _extract_failed_step_log,
    _find_log_content,
    _strip_timestamps,
    build_ci_error_details,
    truncate_ci_details,
)
from mcp_workspace.github_operations.ci_results_manager import CIResultsManager
from mcp_workspace.github_operations.issues import IssueData, IssueManager
from mcp_workspace.github_operations.pr_manager import PullRequestManager
from mcp_workspace.workflows.task_tracker import (
    TaskTrackerFileNotFoundError,
    TaskTrackerSectionNotFoundError,
    TaskTrackerStatus,
    get_task_counts,
)

logger = logging.getLogger(__name__)

DEFAULT_LABEL = "unknown"
EMPTY_RECOMMENDATIONS: List[str] = []


class CIStatus(str, Enum):
    """CI pipeline status."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    PENDING = "PENDING"


@dataclass(frozen=True)
class WaitContext:
    """Describes how long the orchestrator waited on CI/PR polling."""

    pr_elapsed: Optional[float] = None
    pr_timeout: int = 0
    ci_elapsed: Optional[float] = None
    ci_timeout: int = 0


@dataclass(frozen=True)
class BranchStatusReport:
    """Branch readiness status report."""

    branch_name: str
    base_branch: str
    ci_status: CIStatus
    ci_details: Optional[str]
    rebase_needed: bool
    rebase_reason: str
    tasks_status: TaskTrackerStatus
    tasks_reason: str
    tasks_is_blocking: bool
    current_github_label: str
    recommendations: List[str]
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    pr_found: Optional[bool] = None
    pr_mergeable: Optional[bool] = None
    pr_mergeable_state: Optional[str] = None
    pr_feedback_text: Optional[str] = None
    pr_feedback_blocks_merge: bool = False

    def format_for_human(
        self,
        wait_context: Optional["WaitContext"] = None,
    ) -> str:
        """Format report for human consumption.

        Args:
            wait_context: Optional polling context; renders a ``Wait:`` line
                between ``Base Branch:`` and the report header.

        Returns:
            Formatted string with status icons and recommendations.
        """
        # Determine status icons
        ci_icon_map: Dict[CIStatus, str] = {
            CIStatus.PASSED: "\u2705",
            CIStatus.FAILED: "\u274c",
            CIStatus.PENDING: "\u23f3",
            CIStatus.NOT_CONFIGURED: "\u2699\ufe0f",
        }
        ci_icon = ci_icon_map.get(self.ci_status, "\u2753")

        rebase_icon = "\u2705" if not self.rebase_needed else "\u26a0\ufe0f"
        rebase_status_text = "UP TO DATE" if not self.rebase_needed else "BEHIND"

        tasks_icon_map = {
            TaskTrackerStatus.COMPLETE: "\u2705",
            TaskTrackerStatus.INCOMPLETE: "\u274c",
            TaskTrackerStatus.ERROR: "\u26a0\ufe0f",
        }
        if self.tasks_status == TaskTrackerStatus.N_A:
            tasks_icon = "\u26a0\ufe0f" if self.tasks_is_blocking else "\u2796"
        else:
            tasks_icon = tasks_icon_map.get(self.tasks_status, "\u2753")
        tasks_status_text = self.tasks_status.value

        # Build the report sections - Branch info first
        lines: List[str] = [
            f"Branch: {self.branch_name}",
            f"Base Branch: {self.base_branch}",
        ]
        wait_line = _format_wait_line(self, wait_context)
        if wait_line is not None:
            lines.append(wait_line)
        lines.extend(
            [
                "",
                "Branch Status Report",
                "",
            ]
        )

        # PR section (only when pr_found is not None)
        if self.pr_found is not None:
            if self.pr_found:
                lines.append(f"PR: \u2705 #{self.pr_number} ({self.pr_url})")
                if self.pr_mergeable is True:
                    lines.append("Merge Status: \u2705 Mergeable (squash-merge safe)")
                elif self.pr_mergeable is False:
                    lines.append("Merge Status: \u274c Not mergeable (has conflicts)")
                else:
                    lines.append("Merge Status: \u23f3 Pending")
                if self.pr_mergeable_state is not None:
                    lines.append(f"Mergeable State: {self.pr_mergeable_state}")
                if self.pr_feedback_text is not None:
                    lines.append("")
                    lines.append(self.pr_feedback_text)
            else:
                lines.append("PR: \u274c No PR found")
            lines.append("")

        lines.append(f"CI Status: {ci_icon} {self.ci_status.value}")

        # Add CI details if they exist
        if self.ci_details:
            lines.extend(
                [
                    "",
                    "CI Error Details:",
                    self.ci_details,
                ]
            )

        lines.extend(
            [
                "",
                f"Rebase Status: {rebase_icon} {rebase_status_text}",
                f"- {self.rebase_reason}",
                "",
                f"Task Tracker: {tasks_icon} {tasks_status_text} ({self.tasks_reason})",
                "",
                f"GitHub Status: {self.current_github_label}",
                "",
                "Recommendations:",
            ]
        )

        # Add recommendations
        for recommendation in self.recommendations:
            lines.append(f"- {recommendation}")

        return "\n".join(lines)

    def format_for_llm(
        self,
        max_lines: int = 300,
        wait_context: Optional["WaitContext"] = None,
    ) -> str:
        """Format report for LLM consumption with truncation.

        Args:
            max_lines: Maximum number of lines for CI error details.
            wait_context: Optional polling context; renders a ``Wait:`` line
                directly below the ``Branch Status:`` summary line.

        Returns:
            Compact formatted string optimized for LLM context windows.
        """
        # Convert rebase_needed to status string
        rebase_status = "BEHIND" if self.rebase_needed else "UP_TO_DATE"

        # Build status summary line
        status_summary = (
            f"Branch Status: CI={self.ci_status.value}, Rebase={rebase_status}, "
            f"Tasks={self.tasks_status.value} ({self.tasks_reason})"
        )
        if self.pr_found is True:
            mergeable_str = (
                str(self.pr_mergeable) if self.pr_mergeable is not None else "None"
            )
            status_summary += f", PR=#{self.pr_number}, Mergeable={mergeable_str}"
            if self.pr_mergeable_state is not None:
                status_summary += f", Mergeable_State={self.pr_mergeable_state}"
        elif self.pr_found is False:
            status_summary += ", PR=NOT_FOUND"
        recommendations_text = ", ".join(self.recommendations)

        # Branch info on first line
        lines: List[str] = [
            f"Branch: {self.branch_name} | Base: {self.base_branch}",
            status_summary,
        ]
        wait_line = _format_wait_line(self, wait_context)
        if wait_line is not None:
            lines.append(wait_line)
        lines.extend(
            [
                f"GitHub Label: {self.current_github_label}",
                f"Recommendations: {recommendations_text}",
            ]
        )

        if self.pr_feedback_text is not None:
            lines.append("")
            lines.append(self.pr_feedback_text)

        # Add CI details if they exist, with truncation and footer
        if self.ci_details:
            truncated_details = truncate_ci_details(self.ci_details, max_lines)
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


def _format_wait_line(
    report: BranchStatusReport,
    wait_context: Optional[WaitContext],
) -> Optional[str]:
    """Build the ``Wait: ...`` line, or None when nothing to render."""
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


def create_empty_report() -> BranchStatusReport:
    """Create an empty/default report for error cases."""
    return BranchStatusReport(
        branch_name="unknown",
        base_branch="unknown",
        ci_status=CIStatus.NOT_CONFIGURED,
        ci_details=None,
        rebase_needed=False,
        rebase_reason="Unknown",
        tasks_status=TaskTrackerStatus.N_A,
        tasks_reason="Unknown",
        tasks_is_blocking=False,
        current_github_label=DEFAULT_LABEL,
        recommendations=EMPTY_RECOMMENDATIONS,
    )


def get_failed_jobs_summary(
    jobs: Sequence[Mapping[str, Any]], logs: Mapping[str, str]
) -> Dict[str, Any]:
    """Summarize failed jobs from CI results.

    Args:
        jobs: List of job data dictionaries from CI status.
        logs: Dictionary mapping log filenames to contents.

    Returns:
        Dictionary with job_name, step_name, step_number, log_excerpt,
        and other_failed_jobs list.
    """
    failed = [j for j in jobs if j.get("conclusion") == "failure"]
    if not failed:
        return {
            "job_name": "",
            "step_name": "",
            "step_number": 0,
            "log_excerpt": "",
            "other_failed_jobs": [],
        }

    # Get first failed job
    first_failed = failed[0]
    job_name = str(first_failed.get("name", ""))

    # Find first step with conclusion == "failure"
    step_name = ""
    step_number = 0
    steps = first_failed.get("steps", [])
    for step in steps:
        if step.get("conclusion") == "failure":
            step_name = str(step.get("name", ""))
            step_number = step.get("number", 0)
            break

    log_content = _find_log_content(logs, job_name, step_number, step_name)

    # Strip timestamps first so ##[group] markers are parseable
    if log_content:
        log_content = _strip_timestamps(log_content)

    # Extract just the failed step's section from the full job log
    if log_content:
        extracted = _extract_failed_step_log(log_content, step_name)
        if extracted:
            log_content = extracted

    log_excerpt = truncate_ci_details(log_content)

    # Other failed jobs
    other_failed_jobs = [str(j.get("name", "")) for j in failed[1:]]

    return {
        "job_name": job_name,
        "step_name": step_name,
        "step_number": step_number,
        "log_excerpt": log_excerpt,
        "other_failed_jobs": other_failed_jobs,
    }


def _collect_ci_status(
    project_dir: Path, branch_name: str, max_log_lines: int
) -> tuple[CIStatus, Optional[str]]:
    """Collect CI status and details.

    Returns:
        Tuple of (CIStatus, optional details string).
    """
    try:
        ci_manager = CIResultsManager(project_dir=project_dir)
        status_result = ci_manager.get_latest_ci_status(branch_name)
        run_data = status_result.get("run")

        if run_data is None or len(run_data) == 0:
            return CIStatus.NOT_CONFIGURED, None

        ci_state = run_data.get("conclusion") or run_data.get("status", "")

        if ci_state == "success":
            return CIStatus.PASSED, None
        elif ci_state == "failure":
            try:
                details = build_ci_error_details(
                    ci_manager, status_result, max_lines=max_log_lines
                )
            except Exception:  # pylint: disable=broad-exception-caught
                details = None
            return CIStatus.FAILED, details
        elif ci_state in ("in_progress", "queued", "pending"):
            return CIStatus.PENDING, None
        else:
            return CIStatus.NOT_CONFIGURED, None

    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("CI status collection failed", exc_info=True)
        return CIStatus.NOT_CONFIGURED, None


def _collect_rebase_status(project_dir: Path, base_branch: str) -> tuple[bool, str]:
    """Collect rebase status.

    Returns:
        Tuple of (needs_rebase, reason).
    """
    try:
        rebase_needed, reason = needs_rebase(project_dir, target_branch=base_branch)
        return rebase_needed, reason
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Rebase check failed", exc_info=True)
        return False, f"Error checking rebase status: {e}"


def _collect_task_status(
    project_dir: Path,
) -> tuple[TaskTrackerStatus, str, bool]:
    """Collect task tracker status.

    Returns:
        Tuple of (status, reason, is_blocking).
    """
    pr_info_path = project_dir / "pr_info"
    if not pr_info_path.exists():
        return TaskTrackerStatus.N_A, "No pr_info folder found", False

    steps_dir = pr_info_path / "steps"
    has_steps_files = (
        any(p.is_file() for p in steps_dir.iterdir()) if steps_dir.exists() else False
    )

    if not has_steps_files:
        return TaskTrackerStatus.N_A, "No implementation plan found", False

    try:
        total, completed = get_task_counts(str(pr_info_path))
        if total == 0:
            return TaskTrackerStatus.N_A, "Task tracker is empty", True
        if completed == total:
            return (
                TaskTrackerStatus.COMPLETE,
                f"All {total} tasks complete",
                False,
            )
        return (
            TaskTrackerStatus.INCOMPLETE,
            f"{completed} of {total} tasks complete",
            True,
        )
    except TaskTrackerFileNotFoundError:
        logger.info("No TASK_TRACKER.md but steps files exist — blocking")
        return (
            TaskTrackerStatus.N_A,
            "Create task tracker \u2014 implementation plan exists but no TASK_TRACKER.md",
            True,
        )
    except TaskTrackerSectionNotFoundError:
        logger.info("No Tasks section in tracker — blocking=%s", has_steps_files)
        return (
            TaskTrackerStatus.N_A,
            "TASK_TRACKER.md has no Tasks section",
            has_steps_files,
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Task tracker check failed", exc_info=True)
        return TaskTrackerStatus.ERROR, f"Could not read task tracker: {e}", True


def _collect_github_label(issue_data: Optional[IssueData]) -> str:
    """Extract the current status label from issue data.

    Returns:
        Current status label string, or DEFAULT_LABEL if not found.
    """
    if issue_data is None:
        return DEFAULT_LABEL
    labels = issue_data.get("labels", [])
    for label in labels:
        if isinstance(label, str) and label.startswith("status-"):
            return label
    return DEFAULT_LABEL


def _collect_pr_info(
    pr_manager: PullRequestManager, branch_name: str
) -> tuple[Optional[int], Optional[str], Optional[bool], Optional[bool], Optional[str]]:
    """Collect PR info for the branch.

    Returns:
        Tuple of (pr_number, pr_url, pr_found, pr_mergeable, pr_mergeable_state).
    """
    try:
        prs = pr_manager.find_pull_request_by_head(branch_name)
        if prs:
            pr = prs[0]
            return (
                pr["number"],
                pr["url"],
                True,
                pr.get("mergeable"),
                pr.get("mergeable_state"),
            )
        return (None, None, False, None, None)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("PR lookup failed", exc_info=True)
        return (None, None, None, None, None)


def _apply_pr_merge_override(
    rebase_needed: bool,
    rebase_reason: str,
    pr_mergeable: Optional[bool],
) -> tuple[bool, str]:
    """Override rebase status when PR is mergeable on GitHub.

    When the branch is behind but GitHub confirms the PR is mergeable
    (e.g. squash-merge), the local rebase check is overridden.

    Args:
        rebase_needed: Whether local git says rebase is needed.
        rebase_reason: Human-readable reason from local check.
        pr_mergeable: GitHub's mergeable status (True/False/None).

    Returns:
        Tuple of (rebase_needed, rebase_reason), possibly overridden.
    """
    if not rebase_needed:
        return (rebase_needed, rebase_reason)
    if pr_mergeable is True:
        return (False, "Behind base branch but PR is mergeable (squash-merge safe)")
    return (rebase_needed, rebase_reason)


def _generate_recommendations(report_data: Dict[str, Any]) -> List[str]:
    """Generate actionable recommendations based on status.

    Returns:
        List of recommendation strings prioritized by importance.
    """
    recommendations: List[str] = []

    ci_status = report_data.get("ci_status")
    rebase_needed = report_data.get("rebase_needed", False)
    tasks_status = report_data.get("tasks_status", TaskTrackerStatus.N_A)
    tasks_reason = report_data.get("tasks_reason", "")
    tasks_is_blocking = report_data.get("tasks_is_blocking", False)
    tasks_ok = not tasks_is_blocking
    pr_mergeable = report_data.get("pr_mergeable")
    pr_blocks = report_data.get("pr_feedback_blocks_merge", False)

    if ci_status == CIStatus.FAILED:
        recommendations.append("Fix CI test failures")
        if report_data.get("ci_details"):
            recommendations.append("Check CI error details above")
    elif ci_status == CIStatus.PENDING:
        recommendations.append("Wait for CI to complete")
    elif ci_status == CIStatus.NOT_CONFIGURED:
        recommendations.append("Configure CI pipeline")

    if tasks_status == TaskTrackerStatus.INCOMPLETE:
        recommendations.append(f"Complete remaining tasks ({tasks_reason})")
    elif tasks_status == TaskTrackerStatus.N_A and tasks_is_blocking:
        recommendations.append(f"Fix task tracker: {tasks_reason}")
    elif tasks_status == TaskTrackerStatus.ERROR:
        recommendations.append(f"Fix task tracker error: {tasks_reason}")

    if rebase_needed and tasks_ok and ci_status != CIStatus.FAILED:
        recommendations.append("Rebase onto origin/main")

    ci_ok = ci_status in (CIStatus.PASSED, CIStatus.NOT_CONFIGURED)
    if ci_ok and tasks_ok:
        if pr_blocks:
            recommendations.append("Address review comments")
        elif not rebase_needed:
            if pr_mergeable is True:
                recommendations.append("Ready to merge (squash-merge safe)")
            else:
                recommendations.append("Ready to merge")

    if not recommendations:
        recommendations.append("Continue with current work")

    return recommendations


def collect_branch_status(
    project_dir: Path, max_log_lines: int = 300
) -> BranchStatusReport:
    """Collect comprehensive branch status from all sources.

    Args:
        project_dir: Path to the project directory.
        max_log_lines: Maximum CI log lines to include.

    Returns:
        A BranchStatusReport dataclass (not a dict).
    """
    try:
        # 1. Get current branch
        branch_name = get_current_branch_name(project_dir)
        if branch_name is None:
            logger.error("Could not determine current branch name")
            return create_empty_report()

        # 2. Fetch issue data once for sharing
        issue_data: Optional[IssueData] = None
        issue_manager: Optional[IssueManager] = None
        pr_manager: Optional[PullRequestManager] = None

        try:
            issue_manager = IssueManager(project_dir=project_dir)
            pr_manager = PullRequestManager(project_dir)
            issue_number = extract_issue_number_from_branch(branch_name)
            if issue_number is not None and issue_manager is not None:
                try:
                    fetched = issue_manager.get_issue(issue_number)
                    if fetched and fetched.get("number", 0) > 0:
                        issue_data = fetched
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.debug("Failed to fetch issue data", exc_info=True)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("GitHub manager initialization failed", exc_info=True)

        # 3. Detect base branch (DI: pass managers)
        base_branch_result = detect_base_branch(
            project_dir,
            current_branch=branch_name,
            issue_data=issue_data,
            issue_manager=issue_manager,
            pr_manager=pr_manager,
        )
        base_branch = base_branch_result if base_branch_result else "unknown"

        # 4. Collect CI status
        ci_status, ci_details = _collect_ci_status(
            project_dir, branch_name, max_log_lines
        )

        # 5. Check rebase status
        rebase_needed, rebase_reason = _collect_rebase_status(project_dir, base_branch)

        # 6. Check task tracker
        tasks_status, tasks_reason, tasks_is_blocking = _collect_task_status(
            project_dir
        )

        # 7. Collect GitHub label
        current_github_label = _collect_github_label(issue_data)

        # 8. Collect PR info
        pr_number, pr_url, pr_found, pr_mergeable, pr_mergeable_state = (
            _collect_pr_info(pr_manager, branch_name)
            if pr_manager
            else (None, None, None, None, None)
        )

        # 9. Apply PR merge override
        rebase_needed, rebase_reason = _apply_pr_merge_override(
            rebase_needed, rebase_reason, pr_mergeable if pr_found else None
        )

        # 10. Collect PR feedback
        if pr_manager and pr_found and pr_number is not None:
            pr_feedback_text, pr_feedback_blocks_merge = collect_pr_feedback(
                pr_manager, pr_number
            )
        else:
            pr_feedback_text, pr_feedback_blocks_merge = None, False

        # 11. Generate recommendations
        report_data: Dict[str, Any] = {
            "ci_status": ci_status,
            "ci_details": ci_details,
            "rebase_needed": rebase_needed,
            "tasks_status": tasks_status,
            "tasks_reason": tasks_reason,
            "tasks_is_blocking": tasks_is_blocking,
            "pr_mergeable": pr_mergeable,
            "pr_feedback_blocks_merge": pr_feedback_blocks_merge,
        }
        recommendations = _generate_recommendations(report_data)

        return BranchStatusReport(
            branch_name=branch_name,
            base_branch=base_branch,
            ci_status=ci_status,
            ci_details=ci_details,
            rebase_needed=rebase_needed,
            rebase_reason=rebase_reason,
            tasks_status=tasks_status,
            tasks_reason=tasks_reason,
            tasks_is_blocking=tasks_is_blocking,
            current_github_label=current_github_label,
            recommendations=recommendations,
            pr_number=pr_number,
            pr_url=pr_url,
            pr_found=pr_found,
            pr_mergeable=pr_mergeable,
            pr_mergeable_state=pr_mergeable_state,
            pr_feedback_text=pr_feedback_text,
            pr_feedback_blocks_merge=pr_feedback_blocks_merge,
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error collecting branch status: {e}")
        return create_empty_report()
