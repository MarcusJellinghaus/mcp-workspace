"""Git workflow orchestration layer.

This module coordinates multiple git operations to accomplish complex workflows.
It serves as Layer 0 in the git operations architecture.

Constraints:
- Can only import from same module (git_operations.*)
- Cannot call external APIs (GitHub, Jenkins, etc.)
- Cannot import from other domains (github_operations, etc.)
- Coordinates multiple git operations for business workflows
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

from git.exc import GitCommandError, InvalidGitRepositoryError

from .branch_queries import get_current_branch_name, get_default_branch_name
from .commits import commit_staged_files
from .core import CommitResult, safe_repo_context
from .remotes import fetch_remote
from .repository_status import get_full_status, is_git_repository
from .staging import stage_all_changes

# Use same logging pattern as other git_operations modules
logger = logging.getLogger(__name__)


def commit_all_changes(message: str, project_dir: Path) -> CommitResult:
    """Orchestrate workflow: stage all unstaged changes and commit them in one operation.

    This is a git workflow orchestration function that combines stage_all_changes()
    and commit_staged_files() workflows into a single operation.

    Args:
        message: Commit message
        project_dir: Path to the project directory containing the git repository

    Returns:
        CommitResult dictionary containing:
        - success: True if staging and commit were both successful, False otherwise
        - commit_hash: Git commit SHA (first 7 characters) if successful, None otherwise
        - error: Error message if failed, None if successful

    Note:
        - First stages all unstaged changes (both modified and untracked files)
        - Then commits the staged files
        - Returns error if either staging or commit phase fails
        - Provides clear error messages indicating which phase failed
        - Requires non-empty commit message (after stripping whitespace)
        - If no unstaged changes exist but staged changes do, will commit staged changes
        - If no changes exist at all, will succeed with no commit hash
    """
    logger.debug(
        "Orchestrating commit all changes workflow with message: %s in %s",
        message,
        project_dir,
    )

    # Validate inputs early (delegate message validation to commit_staged_files)
    if not is_git_repository(project_dir):
        error_msg = f"Directory is not a git repository: {project_dir}"
        logger.error(error_msg)
        return {
            "success": False,
            "commit_hash": None,
            "error": error_msg,
            "error_category": "validation_failed",
        }

    # Check if there are any changes to commit
    status = get_full_status(project_dir)
    if not status["staged"] and not status["modified"] and not status["untracked"]:
        logger.info("No changes to commit")
        return {
            "success": True,
            "commit_hash": None,
            "error": None,
            "error_category": None,
        }

    try:
        # Stage all unstaged changes first (using staging module)
        logger.debug("Staging all unstaged changes")
        staging_result = stage_all_changes(project_dir)

        if not staging_result:
            error_msg = "Failed to stage changes"
            logger.error(error_msg)
            return {
                "success": False,
                "commit_hash": None,
                "error": error_msg,
                "error_category": "validation_failed",
            }

        logger.debug("Successfully staged all changes, proceeding to commit")

        # Commit the staged files (using commits module)
        commit_result = commit_staged_files(message, project_dir)

        if commit_result["success"]:
            logger.debug(
                "Successfully completed commit all changes workflow with hash %s",
                commit_result["commit_hash"],
            )
        else:
            logger.error(
                "Staging succeeded but commit failed: %s", commit_result["error"]
            )

        # Return the commit result directly (success or failure)
        return commit_result

    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        error_msg = f"Unexpected error during commit all changes workflow: {e}"
        logger.error(error_msg)
        return {
            "success": False,
            "commit_hash": None,
            "error": error_msg,
            "error_category": None,
        }


def needs_rebase(
    project_dir: Path, target_branch: Optional[str] = None
) -> Tuple[bool, str]:
    """Detect if current branch needs rebasing onto target branch.

    Args:
        project_dir: Path to git repository
        target_branch: Branch to check against (defaults to auto-detect)

    Returns:
        (needs_rebase, reason) where:
        - needs_rebase: True if rebase is needed, False otherwise
        - reason: Description of status ("up-to-date", "3 commits behind", "error: <reason>")
    """
    logger.debug("Checking if rebase needed in %s", project_dir)

    if not is_git_repository(project_dir):
        error_msg = "not a git repository"
        logger.debug("Not a git repository: %s", project_dir)
        return False, f"error: {error_msg}"

    try:
        # Fetch from remote to ensure we have latest refs
        if not fetch_remote(project_dir):
            error_msg = "failed to fetch from remote"
            logger.warning("Failed to fetch from remote for rebase check")
            return False, f"error: {error_msg}"

        with safe_repo_context(project_dir) as repo:
            # Get current branch
            current_branch = get_current_branch_name(project_dir)
            if not current_branch:
                error_msg = "not on a branch (detached HEAD)"
                logger.debug("Repository is in detached HEAD state")
                return False, f"error: {error_msg}"

            # Determine target branch
            if target_branch is None:
                target_branch = get_default_branch_name(project_dir)
                if not target_branch:
                    error_msg = "cannot determine target branch"
                    logger.debug("Could not determine default branch")
                    return False, f"error: {error_msg}"

            # Don't check rebase against self
            if current_branch == target_branch:
                logger.debug("Current branch is the target branch")
                return False, "up-to-date"

            # Check if origin/target_branch exists
            origin_target = f"origin/{target_branch}"
            try:
                repo.git.rev_parse("--verify", origin_target)
            except GitCommandError:
                error_msg = f"target branch '{origin_target}' not found"
                logger.debug("Target branch not found: %s", origin_target)
                return False, f"error: {error_msg}"

            # Count commits that origin/target has but HEAD doesn't
            try:
                commit_range = f"HEAD..{origin_target}"
                commit_count_output = repo.git.rev_list("--count", commit_range)
                commit_count = int(commit_count_output.strip())

                if commit_count == 0:
                    # No commits in origin/target that aren't in HEAD
                    logger.debug("Current branch is up-to-date with %s", origin_target)
                    return False, "up-to-date"
                elif commit_count == 1:
                    reason = "1 commit behind"
                else:
                    reason = f"{commit_count} commits behind"

                logger.debug(
                    "Current branch is %s %s",
                    commit_count,
                    "commit" if commit_count == 1 else "commits",
                )
                return True, reason

            except (GitCommandError, ValueError) as e:
                error_msg = f"failed to count commits: {e}"
                logger.warning("Failed to count commits for rebase check: %s", e)
                return False, f"error: {error_msg}"

    except (InvalidGitRepositoryError, GitCommandError) as e:
        error_msg = f"git error: {e}"
        logger.error("Git error during rebase check: %s", e)
        return False, f"error: {error_msg}"
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        error_msg = f"unexpected error: {e}"
        logger.error("Unexpected error during rebase check: %s", e)
        return False, f"error: {error_msg}"
