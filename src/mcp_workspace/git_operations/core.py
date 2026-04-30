"""Core utilities and shared infrastructure for git operations."""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal, Optional, TypedDict

from git import Repo

# Use same logging pattern as existing modules (see file_operations.py)
logger = logging.getLogger(__name__)

# Constants for git operations
PLACEHOLDER_HASH = "0" * 7
GIT_SHORT_HASH_LENGTH = 7


# Type alias for commit result structure
class CommitResult(TypedDict):
    """Result of a git commit operation."""

    success: bool
    commit_hash: Optional[str]
    error: Optional[str]
    error_category: Optional[
        Literal["signing_failed", "commit_failed", "validation_failed"]
    ]


# Type alias for git push result structure
class PushResult(TypedDict):
    """Result of a git push operation."""

    success: bool
    error: Optional[str]


def _close_repo_safely(repo: Repo) -> None:
    """Safely close a GitPython repository to prevent handle leaks on Windows."""
    try:
        # Close any active git command processes
        # pylint: disable=protected-access  # GitPython has no public API for process cleanup
        if hasattr(repo, "git") and hasattr(repo.git, "_proc") and repo.git._proc:
            try:
                if repo.git._proc.poll() is None:  # Process still running
                    repo.git._proc.terminate()
                    import time

                    time.sleep(0.1)
                    if repo.git._proc.poll() is None:  # Still running, force kill
                        repo.git._proc.kill()
            except (OSError, AttributeError):
                pass  # Ignore errors during process cleanup
        # pylint: enable=protected-access

        # Close the repository if it has a close method
        if hasattr(repo, "close"):
            repo.close()

    except (
        AttributeError,
        OSError,
        Exception,
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        # Log but don't raise - cleanup should be best effort
        logger.debug("Error during repository cleanup (non-critical): %s", e)


@contextmanager
def safe_repo_context(project_dir: Path) -> Iterator[Repo]:
    """Context manager for safely handling GitPython repository objects.

    Ensures proper cleanup of repository objects to prevent Windows handle issues.

    Args:
        project_dir: Path to the git repository directory

    Yields:
        Repo: GitPython repository object
    """
    repo = None
    try:
        repo = Repo(project_dir, search_parent_directories=False)
        yield repo
    finally:
        if repo:
            _close_repo_safely(repo)


def _normalize_git_path(path: Path, base_dir: Path) -> str:
    """Convert a path to git-compatible format.

    Args:
        path: Path to normalize
        base_dir: Base directory to make path relative to

    Returns:
        Git-compatible path string using forward slashes
    """
    relative_path = path.relative_to(base_dir)
    return str(relative_path).replace("\\", "/")
