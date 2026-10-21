"""PR checks mixin for PullRequestManager.

This module provides the PRChecksMixin class containing the
get_non_green_checks lookup for a pull request's head commit.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from github.GithubException import GithubException
from mcp_coder_utils.log_utils import log_function_call

from ._diagnostics import format_rate_limit_error
from .base_manager import _format_error_message

if TYPE_CHECKING:
    from .pr_manager import PullRequestManager

__all__ = ["PRChecksMixin"]

logger = logging.getLogger(__name__)

_PASSING_CHECK_CONCLUSIONS: frozenset[str] = frozenset(
    {"success", "neutral", "skipped"}
)
PERMISSION_ERROR_TEXT = "token lacks permission (Checks: read / Commit statuses: read)"


def _classify_lookup_error(e: BaseException) -> str:
    """Describe a failed check lookup: rate limit, permission, or generic error."""
    msg = format_rate_limit_error(e)
    if msg is not None:
        return msg
    if isinstance(e, GithubException) and e.status in (401, 403):
        return PERMISSION_ERROR_TEXT
    return _format_error_message(e)


class PRChecksMixin:
    """Mixin providing the get_non_green_checks lookup.

    This mixin is designed to be used with PullRequestManager, which supplies
    _get_repository and _last_repository_error.
    """

    @log_function_call
    def get_non_green_checks(
        self: "PullRequestManager", pr_number: int, head_sha: Optional[str] = None
    ) -> tuple[tuple[str, ...], Optional[str]]:
        """List the commit statuses and check runs on a PR head that are not green.

        Non-green rules:
        - a commit status is non-green unless its state is ``success``;
        - a check run that is not ``completed`` is non-green, reported with its
          status (e.g. ``in_progress``, ``queued``);
        - a completed check run is non-green unless its conclusion is
          ``success``, ``neutral`` or ``skipped``, reported with its conclusion.

        Only the first page of commit statuses is read; check runs are
        iterated across all pages. Never raises: any failure is returned as
        the error element.

        Args:
            pr_number: Pull request number, used to resolve the head SHA
            head_sha: Head commit SHA; skips the PR lookup when given

        Returns:
            ``(names, None)`` on success, each name formatted as
            ``"name (state)"``, statuses first, then check runs, in API order;
            ``((), reason)`` when the lookup fails.
        """
        try:
            repo = self._get_repository()
            if repo is None:
                return ((), self._last_repository_error or "repository not accessible")
            sha = head_sha or repo.get_pull(pr_number).head.sha
            commit = repo.get_commit(sha)
            names = [
                f"{s.context} ({s.state})"
                for s in commit.get_combined_status().statuses
                if s.state != "success"
            ]
            for run in commit.get_check_runs():
                if run.status != "completed":
                    names.append(f"{run.name} ({run.status})")
                elif run.conclusion not in _PASSING_CHECK_CONCLUSIONS:
                    names.append(f"{run.name} ({run.conclusion})")
            return (tuple(names), None)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.debug("Check lookup failed", exc_info=True)
            return ((), _classify_lookup_error(e))
