"""CI status collection for ``check_branch_status``.

Holds the GitHub-Actions-facing half of branch status: fetching the
latest CI run, detecting staleness against the pushed HEAD, and
summarizing failed jobs/logs. Shared by ``branch_status.py`` (sync
collection) and ``branch_status_polling.py`` (async polling).
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from mcp_workspace.checks.branch_status_rendering import CIStatus
from mcp_workspace.config import get_github_token
from mcp_workspace.git_operations.branch_queries import get_remote_branch_commit_sha
from mcp_workspace.git_operations.commits import get_latest_commit_sha
from mcp_workspace.github_operations.ci_log_parser import (
    _extract_failed_step_log,
    _find_log_content,
    _strip_timestamps,
    build_ci_error_details,
    truncate_ci_details,
)
from mcp_workspace.github_operations.ci_results_manager import CIResultsManager

logger = logging.getLogger(__name__)

__all__ = ["get_failed_jobs_summary"]

_JOB_FAIL_CONCLUSIONS: frozenset[str] = frozenset({"failure", "cancelled", "timed_out"})


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


def _is_stale_ci_run(
    project_dir: Path, branch_name: str, run_commit_sha: Optional[str]
) -> bool:
    """Return True only when HEAD is pushed and the run predates it."""
    if not run_commit_sha:
        return False
    head_sha = get_latest_commit_sha(project_dir)
    if head_sha is None:
        return False
    origin_sha = get_remote_branch_commit_sha(project_dir, branch_name)
    if origin_sha is None or origin_sha != head_sha:
        return False
    return run_commit_sha != head_sha


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
            if status_result.get("lookup_failed"):
                return CIStatus.UNKNOWN, None, []
            return CIStatus.NOT_CONFIGURED, None, []

        if _is_stale_ci_run(project_dir, branch_name, run_data.get("commit_sha")):
            return CIStatus.PENDING, None, []

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
        return CIStatus.UNKNOWN, None, []
