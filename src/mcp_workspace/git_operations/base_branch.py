"""Base branch detection for feature branches.

Detects the base branch using multiple strategies with priority ordering:
1. Linked issue's base_branch field (explicit user intent)
2. GitHub PR base branch (if open PR exists for current branch)
3. Git merge-base (heuristic fallback from git history)
4. Default branch (main/master)
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from mcp_workspace.git_operations.branch_queries import (
    extract_issue_number_from_branch,
    get_current_branch_name,
    get_default_branch_name,
    remote_branch_exists,
)
from mcp_workspace.git_operations.core import safe_repo_context
from mcp_workspace.git_operations.parent_branch_detection import (
    MERGE_BASE_DISTANCE_THRESHOLD,
    detect_parent_branch_via_merge_base,
)

if TYPE_CHECKING:
    from mcp_workspace.github_operations.issues import IssueData, IssueManager
    from mcp_workspace.github_operations.pr_manager import PullRequestManager

logger = logging.getLogger(__name__)


def _detect_from_issue(
    current_branch: str,
    issue_data: Optional["IssueData"],
    issue_manager: Optional["IssueManager"],
) -> Optional[str]:
    """Try to detect base branch from a linked GitHub issue.

    Args:
        current_branch: Current branch name (used to extract issue number)
        issue_data: Pre-fetched issue data (if available)
        issue_manager: IssueManager instance for fetching issue data

    Returns:
        Base branch name from issue, or None if not found
    """
    # If issue_data is provided, check its base_branch field
    if issue_data is not None:
        base = issue_data.get("base_branch")
        if base:
            logger.debug("Detected base branch from provided issue_data: '%s'", base)
            return base

    # If issue_manager is provided, try to fetch issue data from branch name
    if issue_manager is not None:
        issue_number = extract_issue_number_from_branch(current_branch)
        if issue_number is not None:
            logger.debug(
                "Extracted issue number %d from branch '%s'",
                issue_number,
                current_branch,
            )
            try:
                fetched_issue = issue_manager.get_issue(issue_number)
                if fetched_issue and fetched_issue.get("number", 0) > 0:
                    base = fetched_issue.get("base_branch")
                    if base:
                        logger.debug(
                            "Detected base branch from issue #%d: '%s'",
                            issue_number,
                            base,
                        )
                        return base
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug(
                    "Failed to fetch issue #%d for base branch detection",
                    issue_number,
                )

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


# Suppress git's own terminal credential prompt so ls-remote does not wait on
# a human. Passed per call via the `env=` kwarg so nothing leaks into the
# shared Git object's environment.
_LS_REMOTE_ENV = {"GIT_TERMINAL_PROMPT": "0"}


def _origin_still_has_branch(project_dir: Path, branch_name: str) -> Optional[bool]:
    """Ask origin whether a branch still exists there.

    Args:
        project_dir: Path to git repository
        branch_name: Branch name to look for (without 'origin/' prefix)

    Returns:
        True if origin still lists the branch, False if origin answered and the
        branch is gone, None if the question could not be answered.
    """
    try:
        with safe_repo_context(project_dir) as repo:
            # The full ref, not the bare name: 'feature-A' would also match an
            # unrelated 'refs/heads/team/feature-A' and mask the deletion.
            output = str(
                repo.git.ls_remote(
                    "--heads", "origin", f"refs/heads/{branch_name}", env=_LS_REMOTE_ENV
                )
            )
            return bool(output.strip())
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Could not ask origin about branch '%s': %s", branch_name, e)
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

    if _origin_still_has_branch(project_dir, result) is False:
        logger.debug("Discarding merge-base winner '%s': deleted on origin", result)
        return None
    return result


def detect_base_branch(
    project_dir: Path,
    current_branch: Optional[str] = None,
    issue_data: Optional["IssueData"] = None,
    issue_manager: Optional["IssueManager"] = None,
    pr_manager: Optional["PullRequestManager"] = None,
) -> Optional[str]:
    """Detect the base branch for the current feature branch.

    Detection priority:
    1. Linked issue's ``base_branch`` section (explicit user intent)
    2. GitHub PR base branch (if open PR exists for current branch)
    3. Git merge-base (heuristic fallback from git history)
    4. Default branch (main/master)
    5. None if all detection fails

    Args:
        project_dir: Path to git repository
        current_branch: Current branch name (auto-detected if None)
        issue_data: Pre-fetched issue data (optional)
        issue_manager: IssueManager instance for fetching issues (optional,
            skipped if None — avoids upward import from git_operations)
        pr_manager: PullRequestManager instance for finding PRs (optional,
            skipped if None — avoids upward import from git_operations)

    Returns:
        Branch name string, or None if detection fails.
    """
    # Step 1: Resolve current branch
    if current_branch is None:
        current_branch = get_current_branch_name(project_dir)
    if current_branch is None:
        logger.debug("Cannot detect base branch: no current branch (detached HEAD?)")
        return None

    logger.debug("Detecting base branch for '%s'", current_branch)

    # Step 2: Try issue base_branch
    result = _detect_from_issue(current_branch, issue_data, issue_manager)
    if result is not None:
        return result

    # Step 3: Try PR lookup
    result = _detect_from_pr(current_branch, pr_manager)
    if result is not None:
        return result

    # Step 4: Try git merge-base
    result = _detect_from_merge_base(project_dir, current_branch)
    if result is not None:
        return result

    # Step 5: Try default branch
    default = get_default_branch_name(project_dir)
    if default is not None:
        logger.debug("Falling back to default branch: '%s'", default)
        return default

    # Step 6: All detection failed
    logger.debug("All base branch detection methods failed")
    return None
