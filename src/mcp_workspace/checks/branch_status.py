"""Branch status check — comprehensive branch readiness report.

Collects CI status, rebase status, task tracker progress, and GitHub
labels into a single BranchStatusReport dataclass. Used by the
check_branch_status MCP tool.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_workspace.checks.branch_status_ci import (
    _collect_ci_status,
    get_failed_jobs_summary,
)
from mcp_workspace.checks.branch_status_rendering import (
    GITHUB_TOKEN_HINT,
    CIStatus,
    LinkedBranchStatus,
    WaitContext,
    format_check_names,
    format_report_for_human,
    format_report_for_llm,
    linked_branch_blocks,
)
from mcp_workspace.checks.pr_feedback import collect_pr_feedback
from mcp_workspace.git_operations.base_branch import detect_base_branch
from mcp_workspace.git_operations.branch_queries import (
    extract_issue_number_from_branch,
    get_current_branch_name,
    get_default_branch_name,
)
from mcp_workspace.git_operations.workflows import needs_rebase
from mcp_workspace.github_operations import IssueIdentityMismatchError
from mcp_workspace.github_operations.formatters import find_latest_marked_comment
from mcp_workspace.github_operations.issues import (
    ClosingPRRef,
    IssueBranchManager,
    IssueData,
    IssueManager,
    MalformedBaseBranchError,
    parse_base_branch,
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

_BLOCKING_MERGE_STATES: frozenset[str] = frozenset({"unstable", "blocked", "dirty"})

# GitHub computes mergeable_state lazily; one re-read after this delay.
_UNSTABLE_REREAD_DELAY_SECONDS = 5.0


@dataclass(frozen=True)
class BranchStatusReport:
    """Branch readiness status report."""

    branch_name: str
    base_branch: str
    ci_status: CIStatus
    ci_details: Optional[str]
    rebase_needed: Optional[bool]  # None = UNKNOWN (rebase check skipped)
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
    last_automated_note: Optional[str] = None
    closing_pr_candidate: Optional[ClosingPRRef] = None
    base_branch_error: Optional[str] = None
    non_green_checks: Optional[tuple[str, ...]] = None  # None = lookup not run
    non_green_checks_error: Optional[str] = None

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


def _malformed_first_line(body: str) -> str:
    """Return the first line of the malformed Base Branch section ('' if none)."""
    try:
        parse_base_branch(body)
    except MalformedBaseBranchError as exc:
        return exc.content.splitlines()[0]
    return ""


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
) -> tuple[LinkedBranchStatus, tuple[str, ...], Optional[int], Optional[ClosingPRRef]]:
    """Compare the issue's linked branches against the current branch.

    The issue number is extracted from the branch name here and returned to
    the caller, so it is derived once and the renderer never has to re-derive
    it. Every failure is absorbed into ``UNKNOWN``: the outer handler in
    :func:`collect_branch_status` would otherwise discard the whole report.
    ``IssueBranchManager(...)`` itself raises ``ValueError`` when no token is
    configured.

    A linked branch (``linkedBranches``) always wins over a closing PR, even
    if stale or ambiguous — the fallback below is only ever reached when
    ``linkedBranches`` is empty. If no branch is linked, an open PR that
    would close the issue (``Closes #N``) and whose head matches the current
    branch counts as a valid link too.

    Args:
        project_dir: Path to the project directory.
        branch_name: The current branch name.

    Returns:
        Tuple of (state, linked branch names, issue number, closing PR
        candidate). The names tuple is empty for everything except OK,
        MISMATCH and AMBIGUOUS sourced from a linked branch. The closing PR
        candidate is non-None only for LINKED_VIA_PR and for a MISMATCH
        sourced from exactly one non-matching closing PR. The issue number is
        None only for NOT_CHECKED.
    """
    issue_number = extract_issue_number_from_branch(branch_name)
    if issue_number is None:
        return (LinkedBranchStatus.NOT_CHECKED, (), None, None)

    try:
        manager = IssueBranchManager(project_dir=project_dir)
        result = manager.get_linked_branch_and_closing_prs_or_none(issue_number)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("Linked branch lookup failed", exc_info=True)
        return (LinkedBranchStatus.UNKNOWN, (), issue_number, None)

    if result is None:
        return (LinkedBranchStatus.UNKNOWN, (), issue_number, None)
    branches, closing_prs = result

    if len(branches) > 1:
        return (LinkedBranchStatus.AMBIGUOUS, tuple(branches), issue_number, None)
    if branches:
        state = (
            LinkedBranchStatus.OK
            if branches[0] == branch_name
            else LinkedBranchStatus.MISMATCH
        )
        return (state, tuple(branches), issue_number, None)

    matches = [pr for pr in closing_prs if pr.head_ref_name == branch_name]
    if matches:
        return (LinkedBranchStatus.LINKED_VIA_PR, (), issue_number, matches[0])
    if not closing_prs:
        return (LinkedBranchStatus.NOT_LINKED, (), issue_number, None)
    if len(closing_prs) == 1:
        return (LinkedBranchStatus.MISMATCH, (), issue_number, closing_prs[0])
    return (LinkedBranchStatus.MISMATCH, (), issue_number, None)


def _recheck_unstable(
    pr_manager: Optional[PullRequestManager],
    ci_status: CIStatus,
    pr_number: Optional[int],
    pr_mergeable: Optional[bool],
    pr_mergeable_state: Optional[str],
) -> tuple[Optional[bool], Optional[str], Optional[tuple[str, ...]], Optional[str]]:
    """Re-read a possibly stale ``unstable`` once, then look up non-green checks.

    Runs only when CI is PASSED or NOT_CONFIGURED and the state is
    ``unstable``. A re-read is accepted only if it returns a definite state
    (a non-empty string other than ``unknown``), so it can never turn
    ``unstable`` into ``Ready to merge`` by accident. Never raises.

    Returns:
        Tuple of (pr_mergeable, pr_mergeable_state, non_green_checks,
        non_green_checks_error). The last two are None when the lookup did
        not run.
    """
    if (
        pr_manager is None
        or pr_number is None
        or pr_mergeable_state != "unstable"
        or ci_status not in (CIStatus.PASSED, CIStatus.NOT_CONFIGURED)
    ):
        return pr_mergeable, pr_mergeable_state, None, None
    time.sleep(_UNSTABLE_REREAD_DELAY_SECONDS)
    head_sha: Optional[str] = None
    try:
        pr = pr_manager.get_pull_request(pr_number)
        sha = pr.get("head_sha")
        head_sha = sha if isinstance(sha, str) else None
        state = pr.get("mergeable_state")
        if isinstance(state, str) and state and state != "unknown":
            pr_mergeable, pr_mergeable_state = pr.get("mergeable"), state
    except Exception:  # pylint: disable=broad-exception-caught
        # Every error keeps "unstable".
        logger.debug("PR re-read failed", exc_info=True)
    if pr_mergeable_state != "unstable":
        return pr_mergeable, pr_mergeable_state, None, None
    names, error = pr_manager.get_non_green_checks(pr_number, head_sha)
    return pr_mergeable, pr_mergeable_state, names, error


def _apply_pr_merge_override(
    rebase_needed: Optional[bool],
    rebase_reason: str,
    pr_mergeable: Optional[bool],
) -> tuple[Optional[bool], str]:
    """Override rebase status when PR is mergeable on GitHub.

    When the branch is behind but GitHub confirms the PR is mergeable
    (e.g. squash-merge), the local rebase check is overridden. An UNKNOWN
    (``None``) rebase state passes through unchanged.

    Args:
        rebase_needed: Whether local git says rebase is needed; ``None`` if
            the rebase check was skipped.
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


def _merge_state_recommendation(
    state: str, names: Optional[tuple[str, ...]], error: Optional[str]
) -> str:
    """Build the ``Not ready to merge`` text for a blocking mergeable state.

    The non-green check lookup only runs for ``unstable``; when it did not
    run (both fields None) the generic wording is kept.

    Args:
        state: The blocking ``mergeable_state`` value.
        names: Non-green check names from the lookup; None if it did not run.
        error: Lookup failure reason, if any.

    Returns:
        The recommendation string.
    """
    if state != "unstable" or (names is None and error is None):
        return f"Not ready to merge (GitHub mergeable_state: {state})"
    prefix = "CI passed but GitHub reports mergeable_state=unstable"
    if error:
        return f"{prefix} — could not list checks: {error}"
    if names:
        return f"Not ready to merge — non-green checks: {format_check_names(names)}"
    return f"{prefix} — likely stale, re-check"


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
    base_branch_error_issue = report_data.get("base_branch_error_issue")

    if base_branch_error_issue is not None:
        recommendations.append(
            f"Fix the ### Base Branch section in issue #{base_branch_error_issue}"
        )

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
    elif ci_status == CIStatus.UNKNOWN:
        recommendations.append("CI status could not be determined — retry")

    if tasks_status == TaskTrackerStatus.INCOMPLETE:
        recommendations.append(f"Complete remaining tasks ({tasks_reason})")
    elif tasks_status == TaskTrackerStatus.N_A and tasks_is_blocking:
        recommendations.append(f"Fix task tracker: {tasks_reason}")
    elif tasks_status == TaskTrackerStatus.ERROR:
        recommendations.append(f"Fix task tracker error: {tasks_reason}")

    if rebase_needed is True and tasks_ok and ci_status != CIStatus.FAILED:
        if is_default_branch:
            recommendations.append(f"Pull origin/{default_branch_name}")
        else:
            base = report_data.get("base_branch") or default_branch_name
            recommendations.append(f"Rebase onto origin/{base}")

    if pr_blocks:
        recommendations.append("Address review comments")
    if merge_state_blocked:
        recommendations.append(
            _merge_state_recommendation(
                str(pr_mergeable_state),
                report_data.get("non_green_checks"),
                report_data.get("non_green_checks_error"),
            )
        )

    ci_ok = ci_status in (CIStatus.PASSED, CIStatus.NOT_CONFIGURED)
    if (
        ci_ok
        and tasks_ok
        and not pr_blocks
        and not merge_state_blocked
        and rebase_needed is False
        and not linked_branch_blocking
        and base_branch_error_issue is None
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
        last_automated_note: Optional[str] = None

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

                try:
                    comments = issue_manager.get_comments(issue_number)
                    last_automated_note = find_latest_marked_comment(comments)
                except IssueIdentityMismatchError as e:
                    # Mirrors the get_issue branch above — same signal (issue
                    # transferred or renumbered), so it gets the same warning,
                    # not debug.
                    logger.warning("%s", e)
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.debug(
                        "Failed to fetch automated note comment", exc_info=True
                    )
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("GitHub manager initialization failed", exc_info=True)

        # 3. Detect base branch (DI: pass managers). A malformed Base Branch
        # section is surfaced as-is — never replaced by a guessed base.
        base_branch_error = issue_data.get("base_branch_error") if issue_data else None
        base_branch_error_issue: Optional[int] = None
        base_branch_result: Optional[str] = None
        if issue_data is not None and base_branch_error:
            base_branch_error_issue = issue_data["number"]
            first_line = _malformed_first_line(issue_data.get("body") or "")
            base_branch = (
                f"MALFORMED (issue #{base_branch_error_issue}: {first_line!r})"
            )
        else:
            base_branch_result = detect_base_branch(
                project_dir,
                current_branch=branch_name,
                issue_data=issue_data,
                pr_manager=pr_manager,
            )
            base_branch = base_branch_result if base_branch_result else "unknown"

        # 4. Check the issue's linked branch (owns all of its error handling)
        (
            linked_branch_status,
            linked_branches,
            linked_branch_issue_number,
            closing_pr_candidate,
        ) = _collect_linked_branch_status(project_dir, branch_name)

        # 5. Collect CI status
        ci_status, ci_details, ci_failing_job_names = _collect_ci_status(
            project_dir, branch_name, max_log_lines
        )

        # 6. Check rebase status
        rebase_needed: Optional[bool]
        if base_branch_error_issue is not None:
            rebase_needed = None
            rebase_reason = f"base branch malformed in issue #{base_branch_error_issue}"
        else:
            rebase_needed, rebase_reason = _collect_rebase_status(
                project_dir, base_branch
            )

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

        # 9b. Re-read a possibly stale "unstable" and look up non-green checks
        pr_mergeable, pr_mergeable_state, non_green_checks, non_green_checks_error = (
            _recheck_unstable(
                pr_manager, ci_status, pr_number, pr_mergeable, pr_mergeable_state
            )
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
            # Raw detection result: None lets the default-branch fallback
            # fire instead of naming origin/unknown. None when malformed.
            "base_branch": base_branch_result,
            "base_branch_error_issue": base_branch_error_issue,
            "tasks_status": tasks_status,
            "tasks_reason": tasks_reason,
            "tasks_is_blocking": tasks_is_blocking,
            "pr_mergeable": pr_mergeable,
            "pr_mergeable_state": pr_mergeable_state,
            "non_green_checks": non_green_checks,
            "non_green_checks_error": non_green_checks_error,
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
            last_automated_note=last_automated_note,
            closing_pr_candidate=closing_pr_candidate,
            base_branch_error=base_branch_error,
            non_green_checks=non_green_checks,
            non_green_checks_error=non_green_checks_error,
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error collecting branch status: {e}")
        # Collection failed — review state is undeterminable, so surface
        # UNKNOWN (review gate renders UNKNOWN) rather than fail open to a
        # misleading "clean" verdict. UNKNOWN (not UNAVAILABLE) keeps the
        # CI line and recommendations from blaming a missing token, which
        # may well be present.
        return create_empty_report(ci_status=CIStatus.UNKNOWN)
