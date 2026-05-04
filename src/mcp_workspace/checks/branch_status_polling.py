"""Async polling helpers for ``check_branch_status``.

Provides the deadline-aware ``_wait_for_ci`` / ``_wait_for_pr`` primitives
and the ``async_poll_branch_status`` orchestrator that runs them in
parallel before delegating to ``collect_branch_status``.
"""

import asyncio
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Optional

from mcp_workspace.checks.branch_status import (
    WaitContext,
    collect_branch_status,
)
from mcp_workspace.git_operations.branch_queries import (
    get_current_branch_name,
    remote_branch_exists,
)
from mcp_workspace.github_operations.ci_results_manager import CIResultsManager
from mcp_workspace.github_operations.pr_manager import PullRequestManager

logger = logging.getLogger(__name__)

_CI_POLL_INTERVAL = 15
_PR_POLL_INTERVAL = 20
_MAX_CONSECUTIVE_ERRORS = 3


async def _wait_for_ci(project_dir: Path, branch_name: str, timeout: int) -> float:
    """Poll CI status until terminal (success/failure) or timeout.

    Returns:
        Elapsed seconds spent polling.
    """
    logger.info("Waiting for CI on branch=%s (timeout=%ds)", branch_name, timeout)
    ci_manager = CIResultsManager(project_dir=project_dir)
    start = time.monotonic()
    deadline = start + timeout
    errors = 0
    while True:
        if time.monotonic() >= deadline:
            return time.monotonic() - start
        try:
            result = await asyncio.to_thread(
                ci_manager.get_latest_ci_status, branch_name
            )
            errors = 0
            run = result.get("run") if isinstance(result, dict) else None
            if run and run.get("conclusion") in ("success", "failure"):
                logger.info("CI reached terminal state for branch=%s", branch_name)
                return time.monotonic() - start
        except Exception as exc:  # pylint: disable=broad-exception-caught
            errors += 1
            logger.warning("CI poll error for branch=%s: %s", branch_name, exc)
            if errors >= _MAX_CONSECUTIVE_ERRORS:
                return time.monotonic() - start
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return time.monotonic() - start
        await asyncio.sleep(min(_CI_POLL_INTERVAL, remaining))


async def _wait_for_pr(project_dir: Path, branch_name: str, timeout: int) -> float:
    """Poll for PR existence until found or timeout.

    Returns:
        Elapsed seconds spent polling.
    """
    logger.info("Waiting for PR on branch=%s (timeout=%ds)", branch_name, timeout)
    pr_manager = PullRequestManager(project_dir)
    start = time.monotonic()
    deadline = start + timeout
    errors = 0
    while True:
        if time.monotonic() >= deadline:
            return time.monotonic() - start
        try:
            result = await asyncio.to_thread(
                pr_manager.find_pull_request_by_head, branch_name
            )
            errors = 0
            if result:
                logger.info("PR found for branch=%s", branch_name)
                return time.monotonic() - start
        except Exception as exc:  # pylint: disable=broad-exception-caught
            errors += 1
            logger.warning("PR poll error for branch=%s: %s", branch_name, exc)
            if errors >= _MAX_CONSECUTIVE_ERRORS:
                return time.monotonic() - start
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return time.monotonic() - start
        await asyncio.sleep(min(_PR_POLL_INTERVAL, remaining))


async def async_poll_branch_status(
    project_dir: Path,
    max_log_lines: int = 300,
    ci_timeout: int = 0,
    pr_timeout: int = 0,
) -> str:
    """Collect branch status, optionally polling for CI/PR in parallel.

    Returns the report formatted via `format_for_llm()`.
    """
    branch = await asyncio.to_thread(get_current_branch_name, project_dir)

    if branch is None:
        report = await asyncio.to_thread(
            collect_branch_status, project_dir, max_log_lines
        )
        return report.format_for_llm()

    needs_remote = ci_timeout > 0 or pr_timeout > 0
    remote_present = (
        await asyncio.to_thread(remote_branch_exists, project_dir, branch)
        if needs_remote
        else True
    )

    skip_msg: Optional[str] = None
    wait_ctx: Optional[WaitContext] = None
    if needs_remote and not remote_present:
        skip_msg = "Push branch to remote before waiting for PR or CI"
    elif needs_remote:
        ci_elapsed, pr_elapsed = await asyncio.gather(
            _wait_for_ci(project_dir, branch, ci_timeout),
            _wait_for_pr(project_dir, branch, pr_timeout),
        )
        wait_ctx = WaitContext(
            ci_elapsed=ci_elapsed if ci_timeout > 0 else None,
            ci_timeout=ci_timeout,
            pr_elapsed=pr_elapsed if pr_timeout > 0 else None,
            pr_timeout=pr_timeout,
        )

    report = await asyncio.to_thread(collect_branch_status, project_dir, max_log_lines)

    if skip_msg:
        report = replace(report, recommendations=[skip_msg, *report.recommendations])

    return report.format_for_llm(wait_context=wait_ctx)
