"""Git commit operations for creating commits."""

from pathlib import Path
from typing import Optional

from git.exc import GitCommandError, InvalidGitRepositoryError

from .core import GIT_SHORT_HASH_LENGTH, CommitResult, logger, safe_repo_context
from .repository_status import get_staged_changes, is_git_repository


def commit_staged_files(message: str, project_dir: Path) -> CommitResult:
    """Create a commit from currently staged files.

    Args:
        message: Commit message
        project_dir: Path to the project directory containing the git repository

    Returns:
        CommitResult dictionary containing:
        - success: True if commit was created successfully, False otherwise
        - commit_hash: Git commit SHA (first 7 characters) if successful, None otherwise
        - error: Error message if failed, None if successful

    Note:
        - Only commits currently staged files
        - Requires non-empty commit message (after stripping whitespace)
        - Returns commit hash on success
        - Provides error details on failure
        - Uses existing is_git_repository() for validation
        - Uses get_staged_changes() to verify there's content to commit
    """
    logger.debug("Creating commit with message: %s in %s", message, project_dir)

    # Validate inputs
    if not message or not message.strip():
        error_msg = "Commit message cannot be empty or contain only whitespace"
        logger.error(error_msg)
        return {
            "success": False,
            "commit_hash": None,
            "error": error_msg,
            "error_category": None,
        }

    if not is_git_repository(project_dir):
        error_msg = f"Directory is not a git repository: {project_dir}"
        logger.error(error_msg)
        return {
            "success": False,
            "commit_hash": None,
            "error": error_msg,
            "error_category": None,
        }

    try:
        # Check if there are staged files to commit
        staged_files = get_staged_changes(project_dir)
        if not staged_files:
            error_msg = "No staged files to commit"
            logger.error(error_msg)
            return {
                "success": False,
                "commit_hash": None,
                "error": error_msg,
                "error_category": None,
            }

        # Create the commit
        with safe_repo_context(project_dir) as repo:
            commit = repo.index.commit(message.strip())

            # Get short commit hash
            commit_hash = commit.hexsha[:GIT_SHORT_HASH_LENGTH]

            logger.debug(
                "Successfully created commit %s with message: %s",
                commit_hash,
                message.strip(),
            )

            return {
                "success": True,
                "commit_hash": commit_hash,
                "error": None,
                "error_category": None,
            }

    except (InvalidGitRepositoryError, GitCommandError) as e:
        error_msg = f"Git error creating commit: {e}"
        logger.error(error_msg)
        return {
            "success": False,
            "commit_hash": None,
            "error": error_msg,
            "error_category": None,
        }
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        error_msg = f"Unexpected error creating commit: {e}"
        logger.error(error_msg)
        return {
            "success": False,
            "commit_hash": None,
            "error": error_msg,
            "error_category": None,
        }


def get_latest_commit_sha(project_dir: Path) -> Optional[str]:
    """Get the SHA of the current HEAD commit.

    Args:
        project_dir: Path to the git repository

    Returns:
        The full SHA of HEAD, or None if not in a git repository
    """
    try:
        with safe_repo_context(project_dir) as repo:
            return repo.head.commit.hexsha
    except (InvalidGitRepositoryError, GitCommandError, ValueError, OSError):
        return None
