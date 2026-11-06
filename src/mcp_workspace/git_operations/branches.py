"""Branch operations for git repositories."""

from pathlib import Path

from git.exc import GitCommandError, InvalidGitRepositoryError

from .branch_queries import validate_branch_name
from .core import logger, safe_repo_context
from .repository_status import is_git_repository


def create_branch(
    branch_name: str, project_dir: Path, from_branch: str | None = None
) -> bool:
    """Create a new git branch.

    Args:
        branch_name: Name of the branch to create
        project_dir: Path to the project directory containing git repository
        from_branch: Base branch to create from (defaults to current branch)

    Returns:
        True if branch was created successfully, False otherwise
    """
    logger.debug("Creating branch '%s' in %s", branch_name, project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    # Validate branch name
    if not validate_branch_name(branch_name):
        logger.error(
            "Invalid branch name: '%s'. Must be non-empty and cannot contain: ~ ^ : ? * [",
            branch_name,
        )
        return False

    try:
        with safe_repo_context(project_dir) as repo:
            # Check if branch already exists
            existing_branches = [branch.name for branch in repo.branches]
            if branch_name in existing_branches:
                logger.debug("Branch '%s' already exists", branch_name)
                return False

            # Create new branch
            if from_branch:
                # Create from specified base branch
                try:
                    repo.git.checkout("-b", branch_name, from_branch)
                except GitCommandError as e:
                    logger.error(
                        "Failed to create branch from '%s': %s", from_branch, e
                    )
                    return False
            else:
                # Create from current branch
                try:
                    repo.git.checkout("-b", branch_name)
                except GitCommandError as e:
                    logger.error("Failed to create branch: %s", e)
                    return False

            logger.debug("Successfully created branch '%s'", branch_name)
            return True

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.error("Git error creating branch: %s", e)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.error("Unexpected error creating branch: %s", e)
        return False


def checkout_branch(branch_name: str, project_dir: Path) -> bool:
    """Checkout an existing git branch, creating from remote if needed.

    Args:
        branch_name: Name of the branch to checkout
        project_dir: Path to the project directory containing git repository

    Returns:
        True if branch was checked out successfully, False otherwise

    Note:
        If branch doesn't exist locally but exists on origin remote,
        will create a local tracking branch and check it out.
    """
    logger.debug("Checking out branch '%s' in %s", branch_name, project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    # Validate branch name
    if not branch_name or not branch_name.strip():
        logger.error("Branch name cannot be empty")
        return False

    try:
        with safe_repo_context(project_dir) as repo:
            # Check if we're already on the target branch
            try:
                current_branch = repo.active_branch.name
                if current_branch == branch_name:
                    logger.debug("Already on branch '%s'", branch_name)
                    return True
            except TypeError:
                # In detached HEAD state, continue with checkout
                pass

            # Check if branch exists locally
            existing_branches = [branch.name for branch in repo.branches]
            branch_exists_locally = branch_name in existing_branches

            if not branch_exists_locally:
                # Check if branch exists on remote
                logger.debug(
                    "Branch '%s' not found locally, checking remote...", branch_name
                )

                # Fetch remote branches to ensure we have latest
                try:
                    if "origin" in [remote.name for remote in repo.remotes]:
                        repo.remotes.origin.fetch()
                        logger.debug("Fetched latest from origin")
                    else:
                        logger.error("No origin remote found")
                        return False
                except GitCommandError as e:
                    logger.error("Failed to fetch from origin: %s", e)
                    return False

                # Check remote branches
                remote_branches = [ref.name for ref in repo.remotes.origin.refs]
                remote_branch_name = f"origin/{branch_name}"

                if remote_branch_name in remote_branches:
                    logger.debug("Found branch on remote: %s", remote_branch_name)
                    # Create local tracking branch and checkout
                    try:
                        repo.git.checkout("-b", branch_name, remote_branch_name)
                        logger.debug(
                            "Created local tracking branch '%s' from '%s'",
                            branch_name,
                            remote_branch_name,
                        )
                        return True
                    except GitCommandError as e:
                        logger.error("Failed to create tracking branch: %s", e)
                        return False
                else:
                    logger.error(
                        "Branch '%s' does not exist locally or on remote", branch_name
                    )
                    return False

            # Branch exists locally, checkout directly
            try:
                repo.git.checkout(branch_name)
                logger.debug("Successfully checked out branch '%s'", branch_name)
                return True
            except GitCommandError as e:
                logger.error("Failed to checkout branch '%s': %s", branch_name, e)
                return False

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.error("Git error checking out branch: %s", e)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.error("Unexpected error checking out branch: %s", e)
        return False


def delete_branch(
    branch_name: str,
    project_dir: Path,
    force: bool = False,
    delete_remote: bool = False,
) -> bool:
    """Delete a git branch locally and optionally from remote.

    Args:
        branch_name: Name of the branch to delete
        project_dir: Path to the project directory containing git repository
        force: If True, force delete even if branch is not fully merged (default: False)
        delete_remote: If True, also delete the branch from remote origin (default: False)

    Returns:
        True if branch was deleted successfully, False otherwise

    Note:
        - Cannot delete the currently active branch (will return False)
        - With force=False, deletion fails if branch has unmerged changes
        - With delete_remote=True, will attempt to delete from origin remote
    """
    logger.debug(
        "Deleting branch '%s' in %s (force=%s, remote=%s)",
        branch_name,
        project_dir,
        force,
        delete_remote,
    )

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    # Validate branch name
    if not branch_name or not branch_name.strip():
        logger.error("Branch name cannot be empty")
        return False

    try:
        with safe_repo_context(project_dir) as repo:
            # Check if branch exists
            existing_branches = [branch.name for branch in repo.branches]
            if branch_name not in existing_branches:
                logger.debug("Branch '%s' does not exist locally", branch_name)
                return False

            # Cannot delete the currently active branch
            try:
                current_branch = repo.active_branch.name
                if current_branch == branch_name:
                    logger.error(
                        "Cannot delete currently active branch '%s'", branch_name
                    )
                    return False
            except TypeError:
                # In detached HEAD state, can proceed
                pass

            # Delete local branch
            try:
                if force:
                    repo.git.branch("-D", branch_name)
                    logger.debug("Force deleted local branch '%s'", branch_name)
                else:
                    repo.git.branch("-d", branch_name)
                    logger.debug("Deleted local branch '%s'", branch_name)
            except GitCommandError as e:
                logger.error("Failed to delete local branch '%s': %s", branch_name, e)
                return False

            # Delete remote branch if requested
            if delete_remote:
                try:
                    if "origin" in [remote.name for remote in repo.remotes]:
                        repo.git.push("origin", "--delete", branch_name)
                        logger.debug("Deleted remote branch 'origin/%s'", branch_name)
                    else:
                        logger.debug("No origin remote found, skipping remote deletion")
                except GitCommandError as e:
                    # Remote branch might not exist or already deleted
                    logger.debug("Could not delete remote branch: %s", e)
                    # Don't fail the operation if remote deletion fails

            logger.debug("Successfully deleted branch '%s'", branch_name)
            return True

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.error("Git error deleting branch: %s", e)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.error("Unexpected error deleting branch: %s", e)
        return False
