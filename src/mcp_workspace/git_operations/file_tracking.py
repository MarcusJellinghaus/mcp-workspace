"""File tracking operations for git repositories."""

from pathlib import Path

from git.exc import GitCommandError, InvalidGitRepositoryError

from .core import _normalize_git_path, logger, safe_repo_context
from .repository_status import is_git_repository


def is_file_tracked(file_path: Path, project_dir: Path) -> bool:
    """Check if a file is tracked by git.

    Args:
        file_path: Path to the file to check
        project_dir: Project directory containing the git repository

    Returns:
        True if the file is tracked by git, False otherwise
    """
    if not is_git_repository(project_dir):
        return False

    try:
        with safe_repo_context(project_dir) as repo:
            # Get git-compatible path
            try:
                git_path = _normalize_git_path(file_path, project_dir)
            except ValueError:
                # File is outside project directory
                logger.debug(
                    "File %s is outside project directory %s", file_path, project_dir
                )
                return False

            # Use git ls-files to check if file is tracked
            # This returns all files that git knows about (staged or committed)
            try:
                # Use ls-files with the specific file to avoid loading all files
                result = repo.git.ls_files(git_path)
                # If git returns the file path, it's tracked
                return bool(result and git_path in result)
            except GitCommandError:
                # File is not tracked
                return False

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.debug("Git error checking if file is tracked: %s", e)
        return False
    except Exception as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Unexpected error checking if file is tracked: %s", e)
        return False


def git_move(source_path: Path, dest_path: Path, project_dir: Path) -> bool:
    """Move a file using git mv command.

    Args:
        source_path: Source file path
        dest_path: Destination file path
        project_dir: Project directory containing the git repository

    Returns:
        True if the file was moved successfully using git, False otherwise

    Raises:
        GitCommandError: If git mv command fails
    """
    if not is_git_repository(project_dir):
        return False

    try:
        with safe_repo_context(project_dir) as repo:
            # Get git-compatible paths
            try:
                source_git = _normalize_git_path(source_path, project_dir)
                dest_git = _normalize_git_path(dest_path, project_dir)
            except ValueError as e:
                logger.error("Paths must be within project directory: %s", e)
                return False

            # Execute git mv command
            logger.debug("Executing git mv from %s to %s", source_git, dest_git)
            repo.git.mv(source_git, dest_git)

            logger.debug(
                "Successfully moved file using git from %s to %s", source_git, dest_git
            )
            return True

    except GitCommandError as e:
        logger.error("Git move failed: %s", e)
        raise
    except Exception as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.error("Unexpected error during git move: %s", e)
        return False
