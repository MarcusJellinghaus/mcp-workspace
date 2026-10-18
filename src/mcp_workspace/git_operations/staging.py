"""Git staging operations for managing staged changes."""

from pathlib import Path

from git.exc import GitCommandError, InvalidGitRepositoryError

from .core import _normalize_git_path, logger, safe_repo_context
from .repository_status import get_unstaged_changes, is_git_repository


def _chunk_paths(paths: list[str], max_chars: int = 24000) -> list[list[str]]:
    """Split paths into chunks whose joined length stays under max_chars.

    Order-preserving: concatenating the returned chunks reproduces the input list
    exactly. A single path longer than max_chars becomes the sole entry of its own
    chunk rather than being dropped.

    Args:
        paths: Git-relative paths to chunk.
        max_chars: Maximum total character length (space-joined) per chunk.

    Returns:
        List of path chunks. Empty input returns an empty list.
    """
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for path in paths:
        added_len = len(path) + (1 if current else 0)
        if current and current_len + added_len > max_chars:
            chunks.append(current)
            current = []
            current_len = 0
            added_len = len(path)
        current.append(path)
        current_len += added_len
    if current:
        chunks.append(current)
    return chunks


def stage_specific_files(files: list[Path], project_dir: Path) -> bool:
    """Stage specific files for commit.

    Args:
        files: List of file paths to stage
        project_dir: Path to the project directory containing the git repository

    Returns:
        True if all specified files were staged successfully, False otherwise

    Note:
        - Handles both absolute and relative file paths
        - Validates files exist and are within project directory
        - Logs appropriate warnings/errors for failed operations
        - Returns False if any files couldn't be staged (all-or-nothing approach)
    """
    logger.debug("Staging %d specific files in %s", len(files), project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    # Handle empty list - this is a valid no-op case
    if not files:
        logger.debug("No files to stage - success")
        return True

    try:
        with safe_repo_context(project_dir) as repo:
            # Validate and convert all file paths first
            relative_paths = []
            for file_path in files:
                # Check if file exists
                if not file_path.exists():
                    logger.error("File does not exist: %s", file_path)
                    return False

                # Get git-compatible path
                try:
                    git_path = _normalize_git_path(file_path, project_dir)
                    relative_paths.append(git_path)
                except ValueError:
                    logger.error(
                        "File %s is outside project directory %s",
                        file_path,
                        project_dir,
                    )
                    return False

            # Stage all files at once
            logger.debug("Staging files: %s", relative_paths)
            repo.index.add(relative_paths)

            logger.debug(
                "Successfully staged %d files: %s", len(relative_paths), relative_paths
            )
            return True

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.error("Git error staging files: %s", e)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.error("Unexpected error staging files: %s", e)
        return False


def stage_all_changes(project_dir: Path) -> bool:
    """Stage all unstaged changes (both modified and untracked files) for commit.

    Args:
        project_dir: Path to the project directory containing the git repository

    Returns:
        True if all unstaged changes were staged successfully, False otherwise

    Note:
        - Stages both modified tracked files (including deletions) and untracked files
        - Returns True if no unstaged changes exist (no-op case)
        - Uses git add --all to handle deletions properly
        - Returns False if staging operation fails
    """
    logger.debug("Staging all changes in %s", project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    try:
        # Get all unstaged changes
        unstaged_changes = get_unstaged_changes(project_dir)

        # Combine modified and untracked files
        all_unstaged_files = (
            unstaged_changes["modified"] + unstaged_changes["untracked"]
        )

        # If no unstaged changes, this is a successful no-op
        if not all_unstaged_files:
            logger.debug("No unstaged changes to stage - success")
            return True

        # Use git add --all to stage everything including deletions
        # This is more robust than trying to handle individual files
        with safe_repo_context(project_dir) as repo:
            logger.debug(
                "Staging %d unstaged files using git add --all: %s",
                len(all_unstaged_files),
                all_unstaged_files,
            )

            # Use git add --all to stage all changes (additions, modifications, deletions)
            repo.git.add("--all")

            logger.debug(
                "Successfully staged all %d unstaged changes", len(all_unstaged_files)
            )

            return True

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.error("Git error staging all changes: %s", e)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.error("Unexpected error staging all changes: %s", e)
        return False
