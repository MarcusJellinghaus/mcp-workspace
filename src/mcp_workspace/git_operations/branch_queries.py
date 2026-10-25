"""Branch name validation and querying utilities."""

import re
from pathlib import Path
from typing import Optional

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError

from .core import logger, safe_repo_context
from .repository_status import is_git_repository


def extract_issue_number_from_branch(branch_name: str) -> Optional[int]:
    """Extract issue number from branch name pattern '{issue_number}-title'.

    Args:
        branch_name: Branch name to extract issue number from

    Returns:
        Issue number as integer if found, None otherwise

    Example:
        >>> extract_issue_number_from_branch("123-feature-name")
        123
        >>> extract_issue_number_from_branch("feature-branch")
        None
    """
    if not branch_name:
        return None
    match = re.match(r"^(\d+)-", branch_name)
    if match:
        return int(match.group(1))
    return None


def remote_branch_exists(project_dir: Path, branch_name: str) -> bool:
    """Check if a git branch exists on the remote origin.

    Args:
        project_dir: Path to the project directory containing git repository
        branch_name: Name of the branch to check (without 'origin/' prefix)

    Returns:
        True if branch exists on origin remote, False otherwise

    Note:
        Reads local ``origin/*`` refs only — no network access, so the
        answer can be stale in both directions. Returns ``False`` without
        a reason. For an authoritative answer use ``probe_origin_branch``.
    """
    logger.debug(
        "Checking if remote branch '%s' exists in %s", branch_name, project_dir
    )

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    # Validate branch name
    if not branch_name or not branch_name.strip():
        logger.debug("Branch name is empty")
        return False

    try:
        with safe_repo_context(project_dir) as repo:
            # Check if origin remote exists
            if "origin" not in [remote.name for remote in repo.remotes]:
                logger.debug("No origin remote found in %s", project_dir)
                return False

            # Get remote refs
            remote_refs = [ref.name for ref in repo.remotes.origin.refs]
            remote_branch_name = f"origin/{branch_name}"
            exists = remote_branch_name in remote_refs

            if exists:
                logger.debug("Remote branch '%s' exists", remote_branch_name)
            else:
                logger.debug("Remote branch '%s' does not exist", remote_branch_name)

            return exists

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.debug("Git error checking remote branch existence: %s", e)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Unexpected error checking remote branch existence: %s", e)
        return False


def get_remote_branch_commit_sha(project_dir: Path, branch_name: str) -> Optional[str]:
    """Get the commit sha that origin/<branch_name> currently points to.

    Args:
        project_dir: Path to the project directory containing git repository
        branch_name: Name of the branch to check (without 'origin/' prefix)

    Returns:
        Full commit sha as string, or None if the repo, the origin remote,
        or the specific branch ref cannot be resolved
    """
    logger.debug(
        "Getting remote commit sha for branch '%s' in %s", branch_name, project_dir
    )

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return None

    if not branch_name or not branch_name.strip():
        logger.debug("Branch name is empty")
        return None

    try:
        with safe_repo_context(project_dir) as repo:
            if "origin" not in [remote.name for remote in repo.remotes]:
                logger.debug("No origin remote found in %s", project_dir)
                return None

            remote_branch_name = f"origin/{branch_name}"
            for ref in repo.remotes.origin.refs:
                if ref.name == remote_branch_name:
                    return ref.commit.hexsha

            logger.debug("Remote branch '%s' does not exist", remote_branch_name)
            return None

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.debug("Git error getting remote branch commit sha: %s", e)
        return None
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Unexpected error getting remote branch commit sha: %s", e)
        return None


def branch_exists(project_dir: Path, branch_name: str) -> bool:
    """Check if a git branch exists locally.

    Args:
        project_dir: Path to the project directory containing git repository
        branch_name: Name of the branch to check

    Returns:
        True if branch exists locally, False otherwise
    """
    logger.debug("Checking if branch '%s' exists in %s", branch_name, project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    # Validate branch name
    if not branch_name or not branch_name.strip():
        logger.debug("Branch name is empty")
        return False

    try:
        with safe_repo_context(project_dir) as repo:
            # Get list of local branch names
            existing_branches = [branch.name for branch in repo.branches]
            exists = branch_name in existing_branches

            if exists:
                logger.debug("Branch '%s' exists locally", branch_name)
            else:
                logger.debug("Branch '%s' does not exist locally", branch_name)

            return exists

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.debug("Git error checking branch existence: %s", e)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Unexpected error checking branch existence: %s", e)
        return False


def _check_local_default_branches(repo: Repo) -> Optional[str]:
    """Check for common default branch names in local repository.

    Args:
        repo: GitPython repository object

    Returns:
        First found default branch name ("main" or "master"), or None
    """
    # Check for common default branch names
    default_candidates = ["main", "master"]

    try:
        # Get list of all branch names
        branch_names = [branch.name for branch in repo.branches]
        logger.debug("Available local branches: %s", branch_names)

        # Check for default candidates in order of preference
        for candidate in default_candidates:
            if candidate in branch_names:
                logger.debug("Found local default branch: %s", candidate)
                return candidate

        logger.debug("No common default branches found in local repository")
        return None

    except GitCommandError as e:
        logger.debug("Git error checking local branches: %s", e)
        return None


def get_default_branch_name(project_dir: Path) -> Optional[str]:
    """Get the name of the default branch from git remote HEAD reference.

    This checks what git considers the default branch by looking at
    refs/remotes/origin/HEAD, which is the authoritative source for
    the remote's default branch setting. If origin/HEAD is not set up
    (common in test environments), falls back to checking for common
    default branch names.

    Args:
        project_dir: Path to the project directory containing git repository

    Returns:
        Default branch name as string, or None if:
        - Directory is not a git repository
        - No remote origin configured and no local default branches found
        - Error occurs during branch detection

    Note:
        Prefers git symbolic-ref as the authoritative source, but provides
        minimal fallback for test environments where origin/HEAD isn't configured.
    """
    logger.debug("Getting default branch name for %s", project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return None

    try:
        with safe_repo_context(project_dir) as repo:
            # Check if origin remote exists
            if "origin" not in [remote.name for remote in repo.remotes]:
                logger.debug("No origin remote found in %s", project_dir)
                # No origin remote, check for local main/master branches
                result = _check_local_default_branches(repo)
                return result

            # Check symbolic ref for origin/HEAD (authoritative source)
            try:
                # This shows what the remote considers the default branch
                result = str(repo.git.symbolic_ref("refs/remotes/origin/HEAD"))
                # Result looks like: "refs/remotes/origin/main"
                if result.startswith("refs/remotes/origin/"):
                    default_branch = result.replace("refs/remotes/origin/", "")
                    logger.debug(
                        "Found default branch from symbolic-ref: %s", default_branch
                    )
                    return default_branch
            except GitCommandError:
                # origin/HEAD not set, try minimal fallback
                logger.debug(
                    "origin/HEAD not set, checking for common default branches"
                )
                result = _check_local_default_branches(repo)
                return result

            # If we reach here, the symbolic-ref command succeeded but didn't match expected format
            logger.debug("Unexpected symbolic-ref format, checking fallback")
            result = _check_local_default_branches(repo)
            return result

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.debug("Git error getting default branch name: %s", e)
        return None
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Unexpected error getting default branch name: %s", e)
        return None


def get_current_branch_name(project_dir: Path) -> Optional[str]:
    """Get the name of the current active branch.

    Args:
        project_dir: Path to the project directory containing git repository

    Returns:
        Current branch name as string, or None if:
        - Directory is not a git repository
        - Repository is in detached HEAD state
        - Error occurs during branch detection

    Note:
        Uses existing is_git_repository() validation and follows
        established error handling patterns from other functions.

        Returns ``None`` on detached HEAD, where
        ``git rev-parse --abbrev-ref HEAD`` would print ``"HEAD"``.
    """
    logger.debug("Getting current branch name for %s", project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return None

    try:
        with safe_repo_context(project_dir) as repo:
            # Use repo.active_branch to get current branch
            # This will raise TypeError if in detached HEAD state
            current_branch = repo.active_branch.name
            logger.debug("Current branch: %s", current_branch)
            return current_branch

    except TypeError:
        # Detached HEAD state - repo.active_branch raises TypeError
        logger.debug("Repository is in detached HEAD state")
        return None
    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.debug("Git error getting current branch name: %s", e)
        return None
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Unexpected error getting current branch name: %s", e)
        return None


def has_remote_tracking_branch(project_dir: Path) -> bool:
    """Check if the current branch has a remote tracking branch.

    Args:
        project_dir: Path to the project directory containing git repository

    Returns:
        True if the current branch has a remote tracking branch, False otherwise.
    """
    logger.debug("Checking remote tracking branch for %s", project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    try:
        with safe_repo_context(project_dir) as repo:
            tracking = repo.active_branch.tracking_branch()
            has_tracking = tracking is not None
            logger.debug("Has remote tracking branch: %s", has_tracking)
            return has_tracking

    except TypeError:
        # Detached HEAD state
        logger.debug("Repository is in detached HEAD state")
        return False
    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.debug("Git error checking remote tracking branch: %s", e)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Unexpected error checking remote tracking branch: %s", e)
        return False


def validate_branch_name(branch_name: str) -> bool:
    """Validate branch name against git naming rules.

    Args:
        branch_name: Branch name to validate

    Returns:
        True if valid, False otherwise

    Validation rules:
        - Must be non-empty string
        - Cannot contain: ~ ^ : ? * [
    """
    # Check for empty or whitespace-only branch name
    if not branch_name or not branch_name.strip():
        return False

    # Basic branch name validation (GitHub-compatible)
    invalid_chars = ["~", "^", ":", "?", "*", "["]
    if any(char in branch_name for char in invalid_chars):
        return False

    return True
