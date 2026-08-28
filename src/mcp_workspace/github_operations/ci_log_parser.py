"""CI log parser for GitHub Actions workflow logs.

This module parses GitHub Actions log output to extract relevant failure
information. It provides utilities for stripping timestamps, parsing log
groups, extracting failed step logs, and building CI error detail reports.
"""

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from mcp_workspace.github_operations.ci_results_manager import CIResultsManager

logger = logging.getLogger(__name__)

_TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s?")

__all__ = [
    "build_ci_error_details",
    "truncate_ci_details",
    "_find_log_content",
    "_strip_timestamps",
    "_extract_failed_step_log",
]


def _truncation_marker(kept: int, total: int) -> str:
    """Build the one and only CI log truncation marker.

    Shared by `truncate_ci_details` and `build_ci_error_details` so the marker
    has a single spelling. Names `max_log_lines` without a pasteable value:
    `build_ci_error_details` shares one line budget across every failed job,
    so `max_log_lines={total}` would not return this job's full log.

    Args:
        kept: Number of log lines shown.
        total: Number of log lines before truncation.

    Returns:
        The truncation marker line.
    """
    return (
        f"[... {total - kept} lines omitted: showing {kept} of {total} "
        "— raise max_log_lines for more ...]"
    )


def truncate_ci_details(
    details: str, max_lines: int = 300, head_lines: int = 10
) -> str:
    """Truncate CI details with head + tail preservation.

    If the details exceed max_lines, keeps the first head_lines and
    the last (max_lines - head_lines) lines, inserting a truncation marker.

    Args:
        details: The CI details string to potentially truncate.
        max_lines: Maximum number of lines to keep (default 300).
        head_lines: Number of lines to keep from the start (default 10).

    Returns:
        The original string if within limits, or a truncated version
        with head + tail preservation and a marker showing skipped lines.
    """
    if not details:
        return ""

    lines = details.split("\n")
    # max_lines arrives straight from the unvalidated check_branch_status
    # parameter, so clamp it before anything derives from it: a negative cap
    # made head_lines negative (-1 // 2 == -1), so lines[:-1] emitted almost
    # the whole log under a marker reading "showing -1 of {total}".
    max_lines = max(0, max_lines)
    if len(lines) <= max_lines:
        return details

    # min() is a no-op at the default (max_lines=300, head_lines=10); it only
    # fires when the caller's max_log_lines is below 2 * head_lines, where the
    # old arithmetic produced a negative tail_lines and duplicated the log.
    head_lines = min(head_lines, max_lines // 2)
    tail_lines = max_lines - head_lines
    head = lines[:head_lines]
    tail = lines[-tail_lines:] if tail_lines else []

    return "\n".join(head + [_truncation_marker(max_lines, len(lines))] + tail)


def _strip_timestamps(log_content: str) -> str:
    """Strip GitHub Actions timestamps from log lines.

    GitHub Actions log lines are prefixed with timestamps like:
    2024-01-15T10:30:45.1234567Z <actual content>

    Args:
        log_content: Raw log content with timestamps.

    Returns:
        Log content with timestamps stripped from each line.
    """
    lines = log_content.split("\n")
    stripped = [_TIMESTAMP_PATTERN.sub("", line) for line in lines]
    return "\n".join(stripped)


def _parse_groups(log_content: str) -> List[Tuple[str, List[str]]]:
    """Parse GitHub Actions log groups from log content.

    GitHub Actions uses ::group:: and ::endgroup:: markers to create
    collapsible sections in logs.

    Args:
        log_content: Log content potentially containing group markers.

    Returns:
        List of (group_name, lines) tuples. Lines outside groups are
        collected under an empty group name.
    """
    groups: List[Tuple[str, List[str]]] = []
    current_group: Optional[str] = None
    current_lines: List[str] = []

    for line in log_content.split("\n"):
        if line.startswith("##[group]"):
            # Save previous group if it has content
            if current_lines and current_group is not None:
                groups.append((current_group, current_lines))
            elif current_lines and groups:
                # Attach to preceding group
                groups[-1] = (groups[-1][0], groups[-1][1] + current_lines)
            # Start new group - extract name after ##[group]
            current_group = line[len("##[group]") :]
            current_lines = []
        elif line.startswith("##[endgroup]"):
            # End current group
            if current_group is not None:
                groups.append((current_group, current_lines))
            current_group = None
            current_lines = []
        else:
            current_lines.append(line)

    # Don't forget remaining lines - attach to preceding group
    if current_lines:
        if current_group is not None:
            groups.append((current_group, current_lines))
        elif groups:
            groups[-1] = (groups[-1][0], groups[-1][1] + current_lines)

    return groups


def _extract_failed_step_log(log_content: str, step_name: str) -> str:
    """Extract log content for a specific failed step.

    Searches through log groups for a section matching the step name
    using 3-tier matching: exact → prefix → contains. Falls back to
    groups containing ##[error] lines when no name match is found.

    Args:
        log_content: Full log content for a job.
        step_name: Name of the failed step to extract.

    Returns:
        Log content for the matching step, error group content as fallback,
        or empty string if no matches found.
    """
    if not log_content:
        return ""

    groups = _parse_groups(log_content)

    if not groups:
        return ""

    if step_name and step_name.lower() != "unknown":
        step_lower = step_name.lower()

        # Tier 1: Exact match
        for group_name, lines in groups:
            if group_name.lower() == step_lower:
                return "\n".join(lines)

        # Tier 2: Prefix match
        for group_name, lines in groups:
            if group_name.lower().startswith(step_lower):
                return "\n".join(lines)

        # Tier 3: Contains match
        for group_name, lines in groups:
            if step_lower in group_name.lower():
                return "\n".join(lines)

    # 4. Error-group fallback: collect groups that contain ##[error] lines
    error_sections: List[str] = []
    for group_name, lines in groups:
        if any(line.startswith("##[error]") for line in lines):
            error_sections.append(f"--- {group_name} ---")
            error_sections.append("\n".join(lines))

    return "\n".join(error_sections)


def _find_log_content(
    logs: Mapping[str, str],
    job_name: str,
    step_number: int,
    step_name: str,
) -> str:
    """Find log content for a job using GitHub format first, falling back to old format.

    GitHub format: {number}_{job_name}.txt (execution number doesn't match step.number)
    Old format: {job_name}/{step_number}_{step_name}.txt

    Args:
        logs: Dict mapping log filenames to content
        job_name: Name of the job
        step_number: Step number from API (used for old format fallback)
        step_name: Step name (used for old format fallback)

    Returns:
        Log content string, or empty string if not found
    """
    # Try GitHub format first: pattern match on _{job_name}.txt
    matching_files = [f for f in logs.keys() if f.endswith(f"_{job_name}.txt")]

    if matching_files:
        if len(matching_files) > 1:
            logger.warning(
                f"Multiple log files found for job '{job_name}': {matching_files}. "
                f"Using: {matching_files[0]}"
            )
        return logs[matching_files[0]]

    # Fallback to old format: {job_name}/{step_number}_{step_name}.txt
    log_filename = f"{job_name}/{step_number}_{step_name}.txt"
    log_content = logs.get(log_filename, "")

    if not log_content and step_name:
        available_files = list(logs.keys())
        logger.warning(
            f"No log file found for job '{job_name}'. "
            f"Tried: '*_{job_name}.txt' and '{log_filename}'. "
            f"Available: {available_files}"
        )

    return log_content


def build_ci_error_details(
    ci_manager: "CIResultsManager",
    status_result: Mapping[str, object],
    max_lines: int = 300,
) -> Optional[str]:
    """Build structured CI error details with logs for multiple failed jobs.

    Shows logs for as many failed jobs as fit within the line limit.

    Args:
        ci_manager: CIResultsManager instance
        status_result: Result from get_latest_ci_status
        max_lines: Maximum total lines for output (default 300)

    Returns:
        Structured error details string or None if no logs available
    """
    run_data: Mapping[str, Any] = status_result.get("run", {})  # type: ignore[assignment]
    jobs_data: Sequence[Mapping[str, Any]] = status_result.get("jobs", [])  # type: ignore[assignment]
    # Extract GitHub Actions run URL for user navigation
    run_url = str(run_data.get("url", ""))

    # Get all failed jobs
    failed_jobs = [job for job in jobs_data if job.get("conclusion") == "failure"]

    # Collect distinct run_ids from failed jobs, preserving order
    failed_run_ids: List[int] = list(
        dict.fromkeys(j["run_id"] for j in failed_jobs if j.get("run_id"))
    )

    # Fetch logs for up to 3 failed run_ids
    logs: Dict[str, str] = {}
    fetched_run_ids = failed_run_ids[:3]
    for rid in fetched_run_ids:
        try:
            run_logs = ci_manager.get_run_logs(rid)
            logs.update(run_logs)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to get logs for run %d", rid)

    if not failed_jobs:
        logger.info("No failed jobs found in CI results")
        return None

    # Build output sections
    output_lines: List[str] = []
    lines_used = 0
    jobs_shown: List[str] = []
    jobs_truncated: List[str] = []

    # Prepend jobs_fetch_warning if present
    jobs_fetch_warning = run_data.get("jobs_fetch_warning")
    if jobs_fetch_warning:
        output_lines.append(f"WARNING: {jobs_fetch_warning}")
        output_lines.append("")
        lines_used += 2

    # Section 1: Summary header (will be updated at end)
    summary_placeholder_idx = len(output_lines)
    output_lines.append("")  # Placeholder for summary
    output_lines.append("")
    lines_used += 2

    # Add GitHub Actions run URL if available
    if run_url:
        output_lines.append(f"GitHub Actions: {run_url}")
        output_lines.append("")
        lines_used += 2

    # Section 2: Show logs for each failed job until we hit the limit
    for job in failed_jobs:
        job_name = str(job.get("name", "unknown"))

        # Find first failed step
        step_name = "unknown"
        step_number = 0
        for step in job.get("steps", []):
            if step.get("conclusion") == "failure":
                step_name = str(step.get("name", "unknown"))
                step_number = int(str(step.get("number", 0)))
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

        # Calculate how many lines this job's section would take
        job_id = job.get("id")
        has_job_url = bool(run_url and job_id)
        job_header_lines = 4 if has_job_url else 3

        if log_content:
            log_lines = log_content.split("\n")
        elif has_job_url:
            log_lines = [
                "(logs not available locally)",
                f"View on GitHub: {run_url}/job/{job_id}",
            ]
        else:
            log_lines = ["(logs not available)"]

        # Calculate remaining budget for this job
        remaining_budget = (
            max_lines - lines_used - job_header_lines - 5
        )  # Reserve 5 for footer

        if remaining_budget <= 10:
            # Not enough space for meaningful logs, add to truncated list
            jobs_truncated.append(job_name)
            continue

        # Truncate log if needed
        if log_content and len(log_lines) > remaining_budget:
            head_count = min(10, remaining_budget // 6)
            tail_count = remaining_budget - head_count - 1
            truncated_log = (
                log_lines[:head_count]
                + [_truncation_marker(head_count + tail_count, len(log_lines))]
                + log_lines[-tail_count:]
            )
            log_content = "\n".join(truncated_log)
            log_lines = truncated_log

        # Add job section
        output_lines.append(f"## Job: {job_name}")
        if has_job_url:
            output_lines.append(f"View job: {run_url}/job/{job_id}")
        output_lines.append(f"Failed step: {step_name}")
        output_lines.append("")
        if log_content:
            output_lines.append(log_content)
        else:
            output_lines.append("\n".join(log_lines))
        output_lines.append("")

        lines_used += job_header_lines + len(log_lines) + 1
        jobs_shown.append(job_name)

    # Section 3: List jobs that didn't fit
    if jobs_truncated:
        output_lines.append(
            "## Other failed jobs (logs omitted — raise max_log_lines to include them)"
        )
        for trunc_job_name in jobs_truncated:
            for job in failed_jobs:
                if str(job.get("name")) == trunc_job_name:
                    trunc_step_name = "unknown"
                    for step in job.get("steps", []):
                        if step.get("conclusion") == "failure":
                            trunc_step_name = str(step.get("name", "unknown"))
                            break
                    output_lines.append(
                        f'- {trunc_job_name}: step "{trunc_step_name}" failed'
                    )
                    break

    # Update summary placeholder
    all_failed = jobs_shown + jobs_truncated
    output_lines[summary_placeholder_idx] = (
        f"## CI Failure Summary\n"
        f"Failed jobs ({len(all_failed)}): {', '.join(all_failed)}"
    )

    return "\n".join(output_lines)
