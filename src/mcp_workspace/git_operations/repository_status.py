"""Git repository status and staging queries."""

from pathlib import Path

from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from .core import StatusResult, logger, run_git_raw, safe_repo_context
from .porcelain_parsers import parse_status_z


def _failed_status(
    error: str, returncode: int | None = None, stderr: str | None = None
) -> StatusResult:
    """Build a failed StatusResult: never clean, empty lists."""
    return {
        "success": False,
        "error": error,
        "returncode": returncode,
        "stderr": stderr,
        "clean": False,
        "staged": [],
        "modified": [],
        "untracked": [],
    }


def get_working_tree_status(project_dir: Path) -> StatusResult:
    """Get staged, modified and untracked files in one ``git status`` call.

    Untracked files inside new directories are listed individually
    (``-uall``). A file staged and then changed again is in both ``staged``
    and ``modified``; a rename is listed under its new path.

    Args:
        project_dir: Path to the project directory containing the git repository

    Returns:
        StatusResult with repo-relative, forward-slash paths. Any failure
        (non-repository, nonzero git exit) is ``success=False``,
        ``clean=False`` and empty lists; a non-repository has ``returncode``
        and ``stderr`` None.
    """
    logger.debug("Getting working tree status for %s", project_dir)

    try:
        with safe_repo_context(project_dir) as repo:
            returncode, stdout, stderr = run_git_raw(
                repo, "status", "--porcelain=v1", "-z", "-uall"
            )
    except (InvalidGitRepositoryError, NoSuchPathError):
        logger.debug("Not a git repository: %s", project_dir)
        return _failed_status(f"Not a git repository: {project_dir}")

    if returncode != 0:
        logger.debug("git status failed (exit %s): %s", returncode, stderr)
        return _failed_status(
            f"git status failed (exit {returncode})", returncode, stderr
        )

    staged: list[str] = []
    modified: list[str] = []
    untracked: list[str] = []
    for entry in parse_status_z(stdout):
        if entry.index_status == "?" and entry.worktree_status == "?":
            untracked.append(entry.path)
            continue
        if entry.index_status not in " ?!":
            staged.append(entry.path)
        if entry.worktree_status not in " ?!":
            modified.append(entry.path)

    return {
        "success": True,
        "error": None,
        "returncode": returncode,
        "stderr": stderr,
        "clean": not (staged or modified or untracked),
        "staged": staged,
        "modified": modified,
        "untracked": untracked,
    }


def is_working_directory_clean(
    project_dir: Path, ignore_files: list[str] | None = None
) -> bool:
    """Check if working directory has no uncommitted changes.

    Args:
        project_dir: Path to the project directory containing git repository
        ignore_files: Optional list of filenames to ignore when checking for changes.
            Files in this list will not be counted as uncommitted changes.
            Useful for auto-generated files like uv.lock.

    Returns:
        True if no staged, modified, or untracked files exist (after filtering), False otherwise

    Raises:
        ValueError: If the directory is not a git repository

    Note:
        Uses existing get_full_status() for consistency.

        Raises ``ValueError`` only for a non-repository; otherwise it
        inherits get_full_status() error swallowing and returns ``True``
        on error. Do not gate destructive actions (e.g. a directory
        delete) on it; use ``get_working_tree_status``.
    """
    if not is_git_repository(project_dir):
        raise ValueError(f"Directory is not a git repository: {project_dir}")

    status = get_full_status(project_dir)

    # Filter out ignored files from each category
    if ignore_files:
        ignore_set = set(ignore_files)
        staged = [f for f in status["staged"] if f not in ignore_set]
        modified = [f for f in status["modified"] if f not in ignore_set]
        untracked = [f for f in status["untracked"] if f not in ignore_set]
    else:
        staged = status["staged"]
        modified = status["modified"]
        untracked = status["untracked"]

    total_changes = len(staged) + len(modified) + len(untracked)

    return total_changes == 0


def get_full_status(project_dir: Path) -> dict[str, list[str]]:
    """Get comprehensive status of all changes: staged, modified, and untracked files.

    Args:
        project_dir: Path to the project directory

    Returns:
        Dictionary with 'staged', 'modified', and 'untracked' keys containing lists of file paths.
        File paths are relative to project root.
        Returns empty dict if not a git repository.

    Example:
        {
            "staged": ["new_feature.py", "docs/readme.md"],
            "modified": ["existing_file.py"],
            "untracked": ["temp_notes.txt"]
        }

    Note:
        Errors are swallowed into empty lists, so a failure reads as
        "clean". Do not gate destructive actions on it; use
        ``get_working_tree_status``.
    """
    logger.debug("Getting full git status for %s", project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return {"staged": [], "modified": [], "untracked": []}

    try:
        # Use existing functions for consistency and efficiency
        staged_files = get_staged_changes(project_dir)
        unstaged_changes = get_unstaged_changes(project_dir)

        result = {
            "staged": staged_files,
            "modified": unstaged_changes["modified"],
            "untracked": unstaged_changes["untracked"],
        }

        logger.debug(
            "Full status: %d staged, %d modified, %d untracked files",
            len(result["staged"]),
            len(result["modified"]),
            len(result["untracked"]),
        )

        return result

    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Unexpected error getting full git status: %s", e)
        return {"staged": [], "modified": [], "untracked": []}


def get_unstaged_changes(project_dir: Path) -> dict[str, list[str]]:
    """Get list of files with unstaged changes (modified and untracked).

    Args:
        project_dir: Path to the project directory

    Returns:
        Dictionary with 'modified' and 'untracked' keys containing lists of file paths.
        File paths are relative to project root.
        Returns empty dict if not a git repository.
    """
    logger.debug("Getting unstaged changes for %s", project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return {"modified": [], "untracked": []}

    try:
        with safe_repo_context(project_dir) as repo:
            # Use git status --porcelain to get file status
            # Format: XY filename where X=index status, Y=working tree status
            # We want files where Y is not empty (working tree changes)
            # Use -u to show individual untracked files instead of just directories
            status_output = repo.git.status("--porcelain", "-u").splitlines()

            modified_files = []
            untracked_files = []

            for line in status_output:
                if len(line) < 3:
                    continue

                # Parse git status format: XY filename
                _ = line[0]  # Staged changes
                working_status = line[1]  # Working tree changes
                filename = line[3:]  # Skip space and get filename

                # Skip files that are only staged (no working tree changes)
                if working_status == " ":
                    continue

                # Untracked files have '??' status
                if line.startswith("??"):
                    untracked_files.append(filename)
                else:
                    # Any other working tree change (M, D, etc.)
                    modified_files.append(filename)

            logger.debug(
                "Found %d modified and %d untracked files",
                len(modified_files),
                len(untracked_files),
            )

            return {"modified": modified_files, "untracked": untracked_files}

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.debug("Git error getting unstaged changes: %s", e)
        return {"modified": [], "untracked": []}
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Unexpected error getting unstaged changes: %s", e)
        return {"modified": [], "untracked": []}


def get_staged_changes(project_dir: Path) -> list[str]:
    """Get list of files currently staged for commit.

    Args:
        project_dir: Path to the project directory

    Returns:
        List of file paths currently staged for commit, relative to project root.
        Returns empty list if no staged files or if not a git repository.
    """
    logger.debug("Getting staged changes for %s", project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return []

    try:
        with safe_repo_context(project_dir) as repo:
            # Use git diff --cached --name-only to get staged files
            # This shows files that are staged for the next commit
            staged_files = repo.git.diff("--cached", "--name-only").splitlines()

            # Filter out empty strings and ensure we have clean paths
            staged_files = [f for f in staged_files if f.strip()]

            logger.debug("Found %d staged files: %s", len(staged_files), staged_files)
            return staged_files

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.debug("Git error getting staged changes: %s", e)
        return []
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Unexpected error getting staged changes: %s", e)
        return []


def is_git_repository(project_dir: Path) -> bool:
    """Check if the project directory is a git repository.

    Args:
        project_dir: Path to check for git repository

    Returns:
        True if the directory is a git repository, False otherwise

    Note:
        Does not spawn git: opens ``Repo`` with
        ``search_parent_directories=False``. Returns ``True`` for bare
        repositories, where ``git rev-parse --is-inside-work-tree``
        prints ``false``.
    """
    logger.debug("Checking if %s is a git repository", project_dir)

    try:
        with safe_repo_context(project_dir):
            logger.debug("Detected as git repository: %s", project_dir)
            return True
    except InvalidGitRepositoryError:
        logger.debug("Not a git repository: %s", project_dir)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Error checking if directory is git repository: %s", e)
        return False
