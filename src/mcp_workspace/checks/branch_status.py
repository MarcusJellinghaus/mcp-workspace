"""Branch status check — comprehensive branch readiness report.

Collects CI status, rebase status, task tracker progress, and GitHub
labels into a single BranchStatusReport dataclass. Used by the
check_branch_status MCP tool.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from mcp_workspace.checks.branch_status_rendering import (
    GITHUB_TOKEN_HINT,
    CIStatus,
    LinkedBranchStatus,
    WaitContext,
    format_report_for_human,
    format_report_for_llm,
    linked_branch_blocks,
)
from mcp_workspace.checks.pr_feedback import collect_pr_feedback
from mcp_workspace.config import get_github_token
from mcp_workspace.git_operations.base_branch import detect_base_branch
from mcp_workspace.git_operations.branch_queries import (
    extract_issue_number_from_branch,
    get_current_branch_name,
    get_default_branch_name,
)
from mcp_workspace.git_operations.workflows import needs_rebase
from mcp_workspace.github_operations import IssueIdentityMismatchError
from mcp_workspace.github_operations.ci_log_parser import (
    _extract_failed_step_log,
    _find_log_content,
    _strip_timestamps,
    build_ci_error_details,
    truncate_ci_details,
)
from mcp_workspace.github_operations.ci_results_manager import CIResultsManager
from mcp_workspace.github_operations.issues import (
    IssueBranchManager,
    IssueData,
    IssueManager,
)
from mcp_workspace.github_operations.pr_manager import PullRequestManager
from mcp_workspace.workflows.task_tracker import (
    TaskTrackerFileNotFoundError,
    TaskTrackerSectionNotFoundError,
    TaskTrackerStatus,
    get_task_counts,
)

logger = logging.getLogger(__name__)

__all__ = [
    "BranchStatusReport",
    "collect_branch_status",
    "create_empty_report",
    "get_failed_jobs_summary",
]

DEFAULT_LABEL = "unknown"
EMPTY_RECOMMENDATIONS: List[str] = []

# Written by collect_branch_status, read by _generate_recommendations. Named
# once so the two sides cannot drift.
_LINKED_BRANCH_BLOCKS_KEY = "linked_branch_blocks"

_JOB_FAIL_CONCLUSIONS: frozenset[str] = frozenset({"failure", "cancelled", "timed_out"})
_BLOCKING_MERGE_STATES: frozenset[str] = frozenset({"unstable", "blocked", "dirty"})


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
    pr_feedback_undeterminable: bool = False
    linked_branch_status: LinkedBranchStatus = LinkedBranchStatus.NOT_CHECKED
    linked_branches: tuple[str, ...] = ()
    linked_branch_issue_number: Optional[int] = None

    def format_for_human(
        self,
        wait_context: Optional[WaitContext] = None,
        fail_on_reviews: bool = False,
    ) -> str:
        """Format report for human consumption.

        Args:
            wait_context: Optional polling context; renders a ``Wait:`` line
                between ``Base Branch:`` and the report header.
            fail_on_reviews: When True, render a three-state ``Review Gate:``
                header near the top of the report.

        Returns:
            Formatted string with status icons and recommendations.
        """
        return format_report_for_human(self, wait_context, fail_on_reviews)

    def format_for_llm(
        self,
        max_lines: int = 300,
        wait_context: Optional[WaitContext] = None,
        fail_on_reviews: bool = False,
    ) -> str:
        """Format report for LLM consumption with truncation.

        Args:
            max_lines: Maximum number of lines for CI error details.
            wait_context: Optional polling context; renders a ``Wait:`` line
                directly below the ``Branch Status:`` summary line.
            fail_on_reviews: When True, render a three-state ``Review Gate:``
                header directly below the status summary line.

        Returns:
            Compact formatted string optimized for LLM context windows.
        """
        return format_report_for_llm(self, max_lines, wait_context, fail_on_reviews)


def create_empty_report(
    ci_status: CIStatus = CIStatus.NOT_CONFIGURED,
) -> BranchStatusReport:
    """Create an empty/default report for error cases.

    Args:
        ci_status: CI status for the placeholder report. The
            branch-undeterminable and collection-failure paths pass
            ``UNKNOWN`` so the review gate renders ``UNKNOWN`` instead of a
            misleading ``clean``, without misattributing the cause to a
            missing token.

    Returns:
        A BranchStatusReport with placeholder/unknown values.
    """
    return BranchStatusReport(
        branch_name="unknown",
        base_branch="unknown",
        ci_status=ci_status,
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
) -> tuple[CIStatus, Optional[str], List[str]]:
    """Collect CI status and details.

    Returns:
        Tuple of (CIStatus, optional details string, failing job names).
    """
    if get_github_token() is None:
        logger.info("GitHub token not configured — CI status unavailable")
        return CIStatus.UNAVAILABLE, None, []
    try:
        ci_manager = CIResultsManager(project_dir=project_dir)
        status_result = ci_manager.get_latest_ci_status(branch_name)
        run_data = status_result.get("run")

        if run_data is None or len(run_data) == 0:
            return CIStatus.NOT_CONFIGURED, None, []

        jobs_data = status_result.get("jobs", [])
        failing_names = [
            j["name"] for j in jobs_data if j.get("conclusion") in _JOB_FAIL_CONCLUSIONS
        ]
        conclusion = run_data.get("conclusion")
        status = run_data.get("status", "")

        if conclusion == "success":
            if failing_names:
                try:
                    details = build_ci_error_details(
                        ci_manager, status_result, max_lines=max_log_lines
                    )
                except Exception:  # pylint: disable=broad-exception-caught
                    details = None
                return CIStatus.FAILED, details, failing_names
            if run_data.get("jobs_fetch_warning"):
                return CIStatus.PENDING, None, []
            return CIStatus.PASSED, None, []
        if conclusion == "failure":
            try:
                details = build_ci_error_details(
                    ci_manager, status_result, max_lines=max_log_lines
                )
            except Exception:  # pylint: disable=broad-exception-caught
                details = None
            return CIStatus.FAILED, details, failing_names
        if status in ("in_progress", "queued", "pending"):
            return CIStatus.PENDING, None, []
        return CIStatus.NOT_CONFIGURED, None, []

    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("CI status collection failed", exc_info=True)
        return CIStatus.NOT_CONFIGURED, None, []


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
            "Create task tracker — implementation plan exists but no TASK_TRACKER.md",
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


def _collect_linked_branch_status(
    project_dir: Path, branch_name: str
) -> tuple[LinkedBranchStatus, tuple[str, ...], Optional[int]]:
    """Compare the issue's linked branches against the current branch.

    The issue number is extracted from the branch name here and returned to
    the caller, so it is derived once and the renderer never has to re-derive
    it. Every failure is absorbed into ``UNKNOWN``: the outer handler in
    :func:`collect_branch_status` would otherwise discard the whole report.
    ``IssueBranchManager(...)`` itself raises ``ValueError`` when no token is
    configured.

    Args:
        project_dir: Path to the project directory.
        branch_name: The current branch name.

    Returns:
        Tuple of (state, linked branch names, issue number). The names tuple is
        empty for NOT_CHECKED, UNKNOWN and NOT_LINKED; the issue number is None
        only for NOT_CHECKED.
    """
    issue_number = extract_issue_number_from_branch(branch_name)
    if issue_number is None:
        return (LinkedBranchStatus.NOT_CHECKED, (), None)

    try:
        manager = IssueBranchManager(project_dir=project_dir)
        branches = manager.get_linked_branches_or_none(issue_number)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("Linked branch lookup failed", exc_info=True)
        return (LinkedBranchStatus.UNKNOWN, (), issue_number)

    if branches is None:
        return (LinkedBranchStatus.UNKNOWN, (), issue_number)
    if len(branches) > 1:
        return (LinkedBranchStatus.AMBIGUOUS, tuple(branches), issue_number)
    if not branches:
        return (LinkedBranchStatus.NOT_LINKED, (), issue_number)

    state = (
        LinkedBranchStatus.OK
        if branches[0] == branch_name
        else LinkedBranchStatus.MISMATCH
    )
    return (state, tuple(branches), issue_number)


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
    is_default_branch = report_data.get("is_default_branch", False)
    default_branch_name = report_data.get("default_branch_name") or "main"
    pr_mergeable = report_data.get("pr_mergeable")
    pr_blocks = report_data.get("pr_feedback_blocks_merge", False)
    ci_failing_job_names = report_data.get("ci_failing_job_names", [])
    pr_mergeable_state = report_data.get("pr_mergeable_state")
    merge_state_blocked = pr_mergeable_state in _BLOCKING_MERGE_STATES
    linked_branch_blocking = report_data.get(_LINKED_BRANCH_BLOCKS_KEY, False)

    if ci_status == CIStatus.FAILED:
        if ci_failing_job_names:
            recommendations.append(
                f"Fix failing job(s): {', '.join(ci_failing_job_names)}"
            )
        else:
            recommendations.append("Fix CI test failures")
        if report_data.get("ci_details"):
            recommendations.append("Check CI error details above")
    elif ci_status == CIStatus.PENDING:
        recommendations.append("Wait for CI to complete")
    elif ci_status == CIStatus.NOT_CONFIGURED:
        recommendations.append("Configure CI pipeline")
    elif ci_status == CIStatus.UNAVAILABLE:
        recommendations.append(f"Set a GitHub token ({GITHUB_TOKEN_HINT})")

    if tasks_status == TaskTrackerStatus.INCOMPLETE:
        recommendations.append(f"Complete remaining tasks ({tasks_reason})")
    elif tasks_status == TaskTrackerStatus.N_A and tasks_is_blocking:
        recommendations.append(f"Fix task tracker: {tasks_reason}")
    elif tasks_status == TaskTrackerStatus.ERROR:
        recommendations.append(f"Fix task tracker error: {tasks_reason}")

    if rebase_needed and tasks_ok and ci_status != CIStatus.FAILED:
        action = "Pull" if is_default_branch else "Rebase onto"
        recommendations.append(f"{action} origin/{default_branch_name}")

    if pr_blocks:
        recommendations.append("Address review comments")
    if merge_state_blocked:
        recommendations.append(
            f"Not ready to merge (GitHub mergeable_state: {pr_mergeable_state})"
        )

    ci_ok = ci_status in (CIStatus.PASSED, CIStatus.NOT_CONFIGURED)
    if (
        ci_ok
        and tasks_ok
        and not pr_blocks
        and not merge_state_blocked
        and not rebase_needed
        and not linked_branch_blocking
    ):
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
            return create_empty_report(ci_status=CIStatus.UNKNOWN)

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
                except IssueIdentityMismatchError as e:
                    # Must precede the broad catch: this is a ValueError subclass.
                    logger.warning("%s", e)
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

        # 4. Check the issue's linked branch (owns all of its error handling)
        (
            linked_branch_status,
            linked_branches,
            linked_branch_issue_number,
        ) = _collect_linked_branch_status(project_dir, branch_name)

        # 5. Collect CI status
        ci_status, ci_details, ci_failing_job_names = _collect_ci_status(
            project_dir, branch_name, max_log_lines
        )

        # 6. Check rebase status
        rebase_needed, rebase_reason = _collect_rebase_status(project_dir, base_branch)

        # 7. Check task tracker
        tasks_status, tasks_reason, tasks_is_blocking = _collect_task_status(
            project_dir
        )

        # 8. Collect GitHub label
        current_github_label = _collect_github_label(issue_data)

        # 9. Collect PR info
        pr_number, pr_url, pr_found, pr_mergeable, pr_mergeable_state = (
            _collect_pr_info(pr_manager, branch_name)
            if pr_manager
            else (None, None, None, None, None)
        )

        # 10. Apply PR merge override
        rebase_needed, rebase_reason = _apply_pr_merge_override(
            rebase_needed, rebase_reason, pr_mergeable if pr_found else None
        )

        # 11. Collect PR feedback
        if pr_manager and pr_found and pr_number is not None:
            (
                pr_feedback_text,
                pr_feedback_blocks_merge,
                pr_feedback_undeterminable,
            ) = collect_pr_feedback(pr_manager, pr_number)
        else:
            # pr_found is None => the PR lookup raised or the PR/GitHub
            # manager failed to init => review state is undeterminable.
            # pr_found is False => confirmed no PR (nothing to review, so
            # still clean-eligible).
            pr_feedback_text, pr_feedback_blocks_merge = None, False
            pr_feedback_undeterminable = pr_found is None

        # 12. Generate recommendations
        default_branch_name = get_default_branch_name(project_dir)
        report_data: Dict[str, Any] = {
            "ci_status": ci_status,
            "ci_details": ci_details,
            "ci_failing_job_names": ci_failing_job_names,
            "rebase_needed": rebase_needed,
            "tasks_status": tasks_status,
            "tasks_reason": tasks_reason,
            "tasks_is_blocking": tasks_is_blocking,
            "pr_mergeable": pr_mergeable,
            "pr_mergeable_state": pr_mergeable_state,
            "pr_feedback_blocks_merge": pr_feedback_blocks_merge,
            "is_default_branch": branch_name == default_branch_name,
            "default_branch_name": default_branch_name,
            _LINKED_BRANCH_BLOCKS_KEY: linked_branch_blocks(linked_branch_status),
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
            pr_feedback_undeterminable=pr_feedback_undeterminable,
            linked_branch_status=linked_branch_status,
            linked_branches=linked_branches,
            linked_branch_issue_number=linked_branch_issue_number,
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error collecting branch status: {e}")
        # Collection failed — review state is undeterminable, so surface
        # UNKNOWN (review gate renders UNKNOWN) rather than fail open to a
        # misleading "clean" verdict. UNKNOWN (not UNAVAILABLE) keeps the
        # CI line and recommendations from blaming a missing token, which
        # may well be present.
        return create_empty_report(ci_status=CIStatus.UNKNOWN)
