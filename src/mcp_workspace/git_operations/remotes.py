"""Git remote operations for push, fetch, and GitHub URL parsing."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import git
from git.exc import GitCommandError, InvalidGitRepositoryError

from .branch_queries import branch_exists
from .core import logger, safe_repo_context
from .repository_status import get_full_status, is_git_repository

if TYPE_CHECKING:
    from mcp_workspace.utils.repo_identifier import RepoIdentifier


def get_remote_url(project_dir: Path) -> Optional[str]:
    """Get the raw remote origin URL from a git repository.

    Unlike ``get_repository_identifier`` which normalises to a
    RepoIdentifier, this returns the URL exactly as configured (SSH, HTTPS, any host).

    Args:
        project_dir: Path to the project directory containing a git repository.

    Returns:
        The raw origin URL string, or ``None`` if the directory is not a git
        repository or has no origin remote.
    """
    if not is_git_repository(project_dir):
        return None

    try:
        with safe_repo_context(project_dir) as repo:
            if "origin" not in [remote.name for remote in repo.remotes]:
                return None
            return str(repo.remotes.origin.url)
    except (InvalidGitRepositoryError, GitCommandError):
        return None


def clone_repo(url: str, target_path: Path) -> None:
    """Clone a git repository to *target_path*.

    Args:
        url: Remote repository URL to clone.
        target_path: Local filesystem path for the clone.

    Raises:
        ValueError: If *url* is empty, *target_path* is empty, *target_path*
            already exists, or the git clone command fails.
    """
    if not url or not url.strip():
        raise ValueError("URL cannot be empty")
    if not str(target_path) or str(target_path) == ".":
        raise ValueError("Target path cannot be empty")
    if target_path.exists():
        raise ValueError(f"Target path already exists: {target_path}")

    try:
        git.Repo.clone_from(url, str(target_path))
    except GitCommandError as e:
        raise ValueError(f"Failed to clone '{url}': {e}") from e


def git_push(project_dir: Path, force_with_lease: bool = False) -> dict[str, Any]:
    """Push current branch to origin remote.

    Args:
        project_dir: Path to the project directory containing git repository
        force_with_lease: If True, use --force-with-lease for safe force push (default: False)

    Returns:
        Dictionary containing:
        - success: True if push succeeded, False otherwise
        - error: Error message if failed, None if successful
    """
    logger.debug("Pushing current branch to origin for %s", project_dir)

    if not is_git_repository(project_dir):
        error_msg = f"Directory is not a git repository: {project_dir}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

    try:
        with safe_repo_context(project_dir) as repo:
            # Get current branch name
            current_branch = repo.active_branch.name
            logger.debug("Current branch: %s", current_branch)

            # Execute git push origin <current_branch>
            if force_with_lease:
                repo.git.push("--force-with-lease", "origin", current_branch)
                logger.debug(
                    "Successfully force-pushed branch '%s' to origin with lease",
                    current_branch,
                )
            else:
                repo.git.push("origin", current_branch)
                logger.debug(
                    "Successfully pushed branch '%s' to origin", current_branch
                )
            return {"success": True, "error": None}

    except (InvalidGitRepositoryError, GitCommandError) as e:
        error_msg = f"Git error during push: {e}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        error_msg = f"Unexpected error during push: {e}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}


def push_branch(branch_name: str, project_dir: Path, set_upstream: bool = True) -> bool:
    """Push a git branch to origin remote.

    Args:
        branch_name: Name of the branch to push
        project_dir: Path to the project directory containing git repository
        set_upstream: Whether to set upstream tracking branch (default: True)

    Returns:
        True if branch was pushed successfully, False otherwise
    """
    logger.debug("Pushing branch '%s' to origin in %s", branch_name, project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    # Validate branch name
    if not branch_name or not branch_name.strip():
        logger.error("Branch name cannot be empty")
        return False

    try:
        with safe_repo_context(project_dir) as repo:
            # Check if branch exists locally
            if not branch_exists(project_dir, branch_name):
                logger.error("Branch '%s' does not exist locally", branch_name)
                return False

            # Check if origin remote exists
            if "origin" not in [remote.name for remote in repo.remotes]:
                logger.error("No origin remote found")
                return False

            # Push the branch
            try:
                if set_upstream:
                    # Push with upstream tracking
                    repo.git.push("--set-upstream", "origin", branch_name)
                    logger.debug(
                        "Successfully pushed branch '%s' with upstream tracking",
                        branch_name,
                    )
                else:
                    # Push without upstream tracking
                    repo.git.push("origin", branch_name)
                    logger.debug("Successfully pushed branch '%s'", branch_name)

                return True

            except GitCommandError as e:
                logger.error("Failed to push branch '%s': %s", branch_name, e)
                return False

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.error("Git error pushing branch: %s", e)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.error("Unexpected error pushing branch: %s", e)
        return False


def fetch_remote(project_dir: Path, remote: str = "origin") -> bool:
    """Fetch latest changes from remote repository.

    Args:
        project_dir: Path to the project directory containing git repository
        remote: Name of the remote to fetch from (default: "origin")

    Returns:
        True if fetch was successful, False otherwise
    """
    logger.debug("Fetching from remote '%s' in %s", remote, project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    # Validate remote name
    if not remote or not remote.strip():
        logger.error("Remote name cannot be empty")
        return False

    try:
        with safe_repo_context(project_dir) as repo:
            # Check if remote exists
            if remote not in [r.name for r in repo.remotes]:
                logger.error("Remote '%s' not found", remote)
                return False

            # Fetch from remote
            try:
                repo.git.fetch(remote)
                logger.debug("Successfully fetched from remote '%s'", remote)
                return True

            except GitCommandError as e:
                logger.error("Failed to fetch from remote '%s': %s", remote, e)
                return False

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.error("Git error fetching from remote: %s", e)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.error("Unexpected error fetching from remote: %s", e)
        return False


def get_repository_identifier(
    project_dir: Path,
) -> Optional[RepoIdentifier]:
    """Get repository identifier from git remote origin.

    Returns RepoIdentifier if origin is a parseable git URL, None otherwise.

    Args:
        project_dir: Path to the project directory containing git repository

    Returns:
        RepoIdentifier if origin is parseable, None otherwise.
    """
    from mcp_workspace.utils.repo_identifier import RepoIdentifier

    logger.debug("Getting repository identifier for %s", project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return None

    try:
        with safe_repo_context(project_dir) as repo:
            # Check if origin remote exists
            if "origin" not in [remote.name for remote in repo.remotes]:
                logger.debug("No origin remote found in %s", project_dir)
                return None

            # Get origin remote URL
            origin_url = repo.remotes.origin.url
            logger.debug("Found origin URL: %s", origin_url)

            try:
                identifier = RepoIdentifier.from_repo_url(origin_url)
                logger.debug("Parsed repository identifier: %s", identifier)
                return identifier
            except ValueError:
                logger.debug("Could not parse as repository URL: %s", origin_url)
                return None

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.debug("Git error getting repository URL: %s", e)
        return None
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Unexpected error getting repository URL: %s", e)
        return None


_MAX_DIRTY_PATHS_PER_BUCKET = 20


def _format_dirty_tree(project_dir: Path) -> str:
    """Render the uncommitted changes of a working tree as a log block.

    Args:
        project_dir: Path to the project directory containing git repository

    Returns:
        An empty string when the working tree is clean, so callers can append
        it unconditionally. Otherwise a block starting with a newline, then
        ``Working tree:``, then one indented line per non-empty category of
        staged, modified and untracked paths. A category listing more than
        ``_MAX_DIRTY_PATHS_PER_BUCKET`` paths is truncated and annotated with
        the total count.
    """
    status = get_full_status(project_dir)

    lines: list[str] = []
    for label in ("staged", "modified", "untracked"):
        paths = status[label]
        if not paths:
            continue

        shown = paths[:_MAX_DIRTY_PATHS_PER_BUCKET]
        line = f"  {label}: " + ", ".join(shown)
        if len(paths) > _MAX_DIRTY_PATHS_PER_BUCKET:
            line += (
                f" ... showing {_MAX_DIRTY_PATHS_PER_BUCKET} of {len(paths)} {label}"
            )
        lines.append(line)

    if not lines:
        return ""

    return "\nWorking tree:\n" + "\n".join(lines)


def rebase_onto_branch(project_dir: Path, target_branch: str) -> bool:
    """Attempt to rebase current branch onto origin/<target_branch>.

    Fetches from origin, then attempts rebase. If conflicts are detected,
    automatically aborts the rebase. All outcomes are logged internally.

    NOTE: This function was moved from branches.py because it's inherently
    remote-aware (operates on origin/<branch>) and required fetch_remote.

    Args:
        project_dir: Path to the project directory containing git repository
        target_branch: Name of the branch to rebase onto (without 'origin/' prefix)

    Returns:
        True if rebase succeeded or branch is already up-to-date.
        False if rebase was skipped (conflicts, errors, etc.)

    Note:
        This function never raises exceptions - all errors are logged and
        result in False return value. Safe to call without try/except.
    """
    logger.debug(f"Attempting rebase onto origin/{target_branch} in {project_dir}")

    # Validate inputs
    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    if not target_branch or not target_branch.strip():
        logger.debug("Target branch name is empty")
        return False

    try:
        # Fetch from origin first - fetch_remote is now in the same module
        if not fetch_remote(project_dir):
            logger.warning("Skipping rebase: failed to fetch from origin")
            return False

        with safe_repo_context(project_dir) as repo:
            # Attempt rebase onto origin/<target_branch>
            try:
                repo.git.rebase(f"origin/{target_branch}")
                logger.info(f"Successfully rebased onto origin/{target_branch}")
                return True

            except GitCommandError as e:
                error_message = str(e).lower()

                # Check if already up-to-date (some git versions report this)
                if "up to date" in error_message or "up-to-date" in error_message:
                    logger.info(f"Already up-to-date with origin/{target_branch}")
                    return True

                # Check if rebase is in progress (conflicts detected).
                # Use the repository's real git dir: in a linked worktree or a
                # submodule, .git is a file and the rebase state lives elsewhere.
                git_dir = Path(repo.git_dir)
                rebase_merge_dir = git_dir / "rebase-merge"
                rebase_apply_dir = git_dir / "rebase-apply"

                if rebase_merge_dir.exists() or rebase_apply_dir.exists():
                    logger.warning(
                        "Skipping rebase: merge conflicts detected, aborting rebase"
                    )
                    # Abort the rebase to restore original state
                    try:
                        repo.git.rebase("--abort")
                        logger.debug("Successfully aborted rebase")
                    except GitCommandError as abort_error:
                        logger.warning(f"Failed to abort rebase: {abort_error}")
                    return False

                # Other git command error (e.g., invalid branch name)
                logger.warning(f"Skipping rebase: {e}{_format_dirty_tree(project_dir)}")
                return False

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.warning(f"Skipping rebase: {e}")
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning(f"Unexpected error during rebase: {e}")
        return False
