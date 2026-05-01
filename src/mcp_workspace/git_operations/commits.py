"""Git commit operations for creating commits."""

from pathlib import Path
from typing import Literal, Optional

from git.exc import GitCommandError, InvalidGitRepositoryError

from .core import GIT_SHORT_HASH_LENGTH, CommitResult, logger, safe_repo_context
from .repository_status import get_staged_changes, is_git_repository

_SIGNING_KEYWORDS = ("gpg", "signing", "secret key", "signing failed")
_STDERR_LOG_LIMIT = 500


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
        - error_category: One of "signing_failed", "commit_failed",
          "validation_failed", or None on success.

    Note:
        - Only commits currently staged files
        - Requires non-empty commit message (after stripping whitespace)
        - Returns commit hash on success
        - Provides error details on failure
        - Uses existing is_git_repository() for validation
        - Uses get_staged_changes() to verify there's content to commit
        - Uses git porcelain (``repo.git.commit``) so ``commit.gpgsign``,
          ``user.signingkey``, ``gpg.format``, ``gpg.program``, and the
          ``pre-commit`` / ``commit-msg`` hooks are honored. Hooks now run
          by default (the previous plumbing call silently bypassed them).
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
            "error_category": "validation_failed",
        }

    if not is_git_repository(project_dir):
        error_msg = f"Directory is not a git repository: {project_dir}"
        logger.error(error_msg)
        return {
            "success": False,
            "commit_hash": None,
            "error": error_msg,
            "error_category": "validation_failed",
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
                "error_category": "validation_failed",
            }

        # Create the commit via git porcelain so signing config and hooks apply
        with safe_repo_context(project_dir) as repo:
            stripped_message = message.strip()

            config_reader = repo.config_reader()
            commit_gpgsign = config_reader.get_value(
                "commit", "gpgsign", default="<unset>"
            )
            gpg_format = config_reader.get_value("gpg", "format", default="<unset>")
            user_signingkey = config_reader.get_value(
                "user", "signingkey", default="<unset>"
            )

            logger.debug(
                "Invoking git commit with args=('-m', %r); "
                "commit.gpgsign=%s, gpg.format=%s, user.signingkey=%s",
                stripped_message,
                commit_gpgsign,
                gpg_format,
                user_signingkey,
            )

            try:
                repo.git.commit("-m", stripped_message)
            except GitCommandError as e:
                stderr_lower = str(e.stderr or "").lower()
                category: Literal["signing_failed", "commit_failed"] = (
                    "signing_failed"
                    if any(kw in stderr_lower for kw in _SIGNING_KEYWORDS)
                    else "commit_failed"
                )
                logger.debug(
                    "git commit failed: stderr=%r status=%s command=%r",
                    str(e.stderr or "")[:_STDERR_LOG_LIMIT],
                    e.status,
                    e.command,
                )
                error_msg = f"Git error creating commit: {e}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "commit_hash": None,
                    "error": error_msg,
                    "error_category": category,
                }

            commit_hash = repo.head.commit.hexsha[:GIT_SHORT_HASH_LENGTH]

            logger.debug(
                "Successfully created commit %s with message: %s",
                commit_hash,
                stripped_message,
            )

            return {
                "success": True,
                "commit_hash": commit_hash,
                "error": None,
                "error_category": None,
            }

    except InvalidGitRepositoryError as e:
        error_msg = f"Git error creating commit: {e}"
        logger.error(error_msg)
        return {
            "success": False,
            "commit_hash": None,
            "error": error_msg,
            "error_category": "validation_failed",
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
