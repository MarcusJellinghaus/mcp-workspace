"""Base branch detection for feature branches.

Detects the base branch using multiple strategies with priority ordering:
1. Linked issue's base_branch field (explicit user intent), read from the
   caller-supplied ``issue_data``, or fetched through ``issue_manager`` when
   no ``issue_data`` is given. Callers passing ``issue_data`` must check
   ``base_branch_error`` first; a fetched issue with that error is skipped.
2. GitHub PR base branch (if open PR exists for current branch)
3. Git merge-base (heuristic fallback from git history)
4. Default branch (main/master)

``detect_base_branch_with_source`` also reports which strategy answered.
"""

import logging
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from git.exc import GitCommandNotFound

from mcp_workspace.git_operations.branch_queries import (
    extract_issue_number_from_branch,
    get_current_branch_name,
    get_default_branch_name,
    remote_branch_exists,
)
from mcp_workspace.git_operations.parent_branch_detection import (
    MERGE_BASE_DISTANCE_THRESHOLD,
    detect_parent_branch_via_merge_base,
)
from mcp_workspace.git_operations.remotes import probe_origin_branch

if TYPE_CHECKING:
    from mcp_workspace.github_operations.issues import IssueData, IssueManager
    from mcp_workspace.github_operations.pr_manager import PullRequestManager

logger = logging.getLogger(__name__)


class BaseBranchSource(Enum):
    """Which detection strategy produced the base branch."""

    ISSUE = "issue"
    PR = "pr"
    MERGE_BASE = "merge_base"
    DEFAULT = "default"


def _fetch_issue_data(
    issue_manager: "IssueManager", branch: str
) -> Optional["IssueData"]:
    """Fetch the issue linked to ``branch`` via its leading issue number.

    Args:
        issue_manager: IssueManager-like object providing ``get_issue``
        branch: Branch name, e.g. ``123-feature``

    Returns:
        The issue data, or None if the branch has no issue number, the fetch
        failed, or the issue's base branch section is malformed.
    """
    number = extract_issue_number_from_branch(branch)
    if number is None:
        return None
    try:
        issue = issue_manager.get_issue(number)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to fetch issue #%d: %s", number, e)
        return None
    if issue.get("number", 0) <= 0:
        return None
    if issue.get("base_branch_error"):
        logger.debug(
            "Ignoring base branch of issue #%d: %s",
            number,
            issue.get("base_branch_error"),
        )
        return None
    return issue


def _detect_from_issue(issue_data: Optional["IssueData"]) -> Optional[str]:
    """Try to detect base branch from caller-supplied issue data.

    Args:
        issue_data: Pre-fetched issue data (if available)

    Returns:
        Base branch name from issue, or None if not found
    """
    if issue_data is not None:
        base = issue_data.get("base_branch")
        if base:
            logger.debug("Detected base branch from provided issue_data: '%s'", base)
            return base
    return None


def _detect_from_pr(
    current_branch: str,
    pr_manager: Optional["PullRequestManager"],
) -> Optional[str]:
    """Try to detect base branch from an open GitHub PR.

    Args:
        current_branch: Current branch name
        pr_manager: PullRequestManager instance for finding PRs

    Returns:
        Base branch from PR, or None if not found
    """
    if pr_manager is None:
        return None

    try:
        prs = pr_manager.find_pull_request_by_head(current_branch)
        if prs:
            base = prs[0].get("base_branch")
            if base:
                logger.debug(
                    "Detected base branch from PR #%d: '%s'",
                    prs[0].get("number", 0),
                    base,
                )
                return base
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("Failed to find PR for branch '%s'", current_branch)

    return None


def _detect_from_merge_base(
    project_dir: Path,
    current_branch: str,
) -> Optional[str]:
    """Try to detect base branch from git merge-base analysis.

    Args:
        project_dir: Path to git repository
        current_branch: Current branch name

    Returns:
        Parent branch name, or None if no candidate was found within the
        threshold, or the winning candidate was discarded because origin no
        longer has that branch (the caller then falls back to the default
        branch).
    """
    result = detect_parent_branch_via_merge_base(
        project_dir,
        current_branch,
        distance_threshold=MERGE_BASE_DISTANCE_THRESHOLD,
    )
    if not result:
        return None
    logger.debug("Merge-base elected candidate branch: '%s'", result)

    # Never pushed: an empty ls-remote answer would be ambiguous, so don't ask.
    if not remote_branch_exists(project_dir, result):
        return result

    # Without a resolvable default branch there is nothing better to fall back
    # to, and a "gone" verdict would cascade into base_branch="unknown".
    default = get_default_branch_name(project_dir)
    if default is None or default == result:
        return result

    try:
        probe = probe_origin_branch(project_dir, result)
    except (GitCommandNotFound, OSError) as e:
        logger.debug("Could not ask origin about branch '%s': %s", result, e)
        return result
    if probe["exists"] is None:
        logger.debug(
            "Could not ask origin about branch '%s': %s",
            result,
            probe["stderr"] or probe["error"],
        )
        return result
    if not probe["exists"]:
        logger.debug("Discarding merge-base winner '%s': deleted on origin", result)
        return None
    return result


def detect_base_branch_with_source(
    project_dir: Path,
    current_branch: Optional[str] = None,
    issue_data: Optional["IssueData"] = None,
    pr_manager: Optional["PullRequestManager"] = None,
    issue_manager: Optional["IssueManager"] = None,
) -> Optional[tuple[str, BaseBranchSource]]:
    """Detect the base branch for the current feature branch and its source.

    Detection priority:
    1. Linked issue's ``base_branch`` section (explicit user intent)
    2. GitHub PR base branch (if open PR exists for current branch)
    3. Git merge-base (heuristic fallback from git history)
    4. Default branch (main/master)
    5. None if all detection fails

    Args:
        project_dir: Path to git repository
        current_branch: Current branch name (auto-detected if None)
        issue_data: Pre-fetched issue data (optional). Callers must check
            ``base_branch_error`` before calling — a malformed section is not
            this function's concern. If given without a base branch, the
            issue step is skipped and ``issue_manager`` is not consulted.
        pr_manager: PullRequestManager instance for finding PRs (optional,
            skipped if None — avoids upward import from git_operations)
        issue_manager: IssueManager instance (optional). Used only when
            ``issue_data`` is None: the issue number is taken from the branch
            name; a failed fetch or a malformed base branch section skips the
            issue step.

    Returns:
        ``(branch_name, source)``, or None if detection fails.
    """
    # Step 1: Resolve current branch
    if current_branch is None:
        current_branch = get_current_branch_name(project_dir)
    if current_branch is None:
        logger.debug("Cannot detect base branch: no current branch (detached HEAD?)")
        return None

    logger.debug("Detecting base branch for '%s'", current_branch)

    # Step 2: Try issue base_branch
    if issue_data is None and issue_manager is not None:
        issue_data = _fetch_issue_data(issue_manager, current_branch)
    result = _detect_from_issue(issue_data)
    if result is not None:
        return result, BaseBranchSource.ISSUE

    # Step 3: Try PR lookup
    result = _detect_from_pr(current_branch, pr_manager)
    if result is not None:
        return result, BaseBranchSource.PR

    # Step 4: Try git merge-base
    result = _detect_from_merge_base(project_dir, current_branch)
    if result is not None:
        return result, BaseBranchSource.MERGE_BASE

    # Step 5: Try default branch
    default = get_default_branch_name(project_dir)
    if default is not None:
        logger.debug("Falling back to default branch: '%s'", default)
        return default, BaseBranchSource.DEFAULT

    # Step 6: All detection failed
    logger.debug("All base branch detection methods failed")
    return None


def detect_base_branch(
    project_dir: Path,
    current_branch: Optional[str] = None,
    issue_data: Optional["IssueData"] = None,
    pr_manager: Optional["PullRequestManager"] = None,
    issue_manager: Optional["IssueManager"] = None,
) -> Optional[str]:
    """Detect the base branch for the current feature branch.

    Same detection as ``detect_base_branch_with_source``, returning only the
    branch name.

    Args:
        project_dir: Path to git repository
        current_branch: Current branch name (auto-detected if None)
        issue_data: Pre-fetched issue data (optional). Callers must check
            ``base_branch_error`` before calling — a malformed section is not
            this function's concern.
        pr_manager: PullRequestManager instance for finding PRs (optional,
            skipped if None — avoids upward import from git_operations)
        issue_manager: IssueManager instance (optional), used to fetch the
            branch's issue when ``issue_data`` is None.

    Returns:
        Branch name string, or None if detection fails.
    """
    result = detect_base_branch_with_source(
        project_dir,
        current_branch=current_branch,
        issue_data=issue_data,
        pr_manager=pr_manager,
        issue_manager=issue_manager,
    )
    return result[0] if result else None
