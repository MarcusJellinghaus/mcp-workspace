"""Unstable mergeable_state handling for the branch status check.

Re-reads a possibly stale ``unstable`` state once, looks up the non-green
checks, and builds the matching ``Not ready to merge`` recommendation.
"""

import logging
import time
from typing import Optional

from mcp_workspace.checks.branch_status_rendering import CIStatus, format_check_names
from mcp_workspace.github_operations.pr_manager import PullRequestManager

logger = logging.getLogger(__name__)

# GitHub computes mergeable_state lazily; one re-read after this delay.
_UNSTABLE_REREAD_DELAY_SECONDS = 5.0


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
