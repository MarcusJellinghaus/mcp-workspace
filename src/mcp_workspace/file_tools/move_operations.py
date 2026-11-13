"""Move and rename operations for files and directories."""

import logging
import shutil
from pathlib import Path
from typing import Any

from mcp_coder_utils.log_utils import log_function_call

from mcp_workspace.file_tools.directory_utils import is_path_gitignored
from mcp_workspace.file_tools.file_operations import _contains_git_dir_error
from mcp_workspace.file_tools.path_utils import normalize_path

logger = logging.getLogger(__name__)


def _validate_move_parameters(
    source_path: str, destination_path: str, project_dir: Path
) -> tuple[Path, str, Path, str]:
    """Validate and normalize move operation parameters.

    Args:
        source_path: Source file/directory path
        destination_path: Destination path
        project_dir: Project directory path

    Returns:
        Tuple of (src_abs, src_rel, dest_abs, dest_rel)

    Raises:
        ValueError: If paths are invalid, or the source holds a .git entry
        FileNotFoundError: If source doesn't exist
        FileExistsError: If destination already exists
    """  # noqa: DOC501 - _contains_git_dir_error returns the documented ValueError
    # Validate inputs
    if not source_path or not isinstance(source_path, str):
        raise ValueError(
            f"Source path must be a non-empty string, got {type(source_path)}"
        )

    if not destination_path or not isinstance(destination_path, str):
        raise ValueError(
            f"Destination path must be a non-empty string, got {type(destination_path)}"
        )

    if project_dir is None:
        raise ValueError("Project directory cannot be None")

    # Normalize paths (this also validates they're within project_dir)
    src_abs, src_rel = normalize_path(source_path, project_dir)
    dest_abs, dest_rel = normalize_path(destination_path, project_dir)

    # Check if source exists
    if not src_abs.exists():
        raise FileNotFoundError(f"Source file '{source_path}' does not exist")

    git_dir_error = _contains_git_dir_error(src_abs, src_rel)
    if git_dir_error is not None:
        raise git_dir_error

    # Check if destination already exists
    if dest_abs.exists():
        raise FileExistsError(f"Destination '{destination_path}' already exists")

    return src_abs, src_rel, dest_abs, dest_rel


def _determine_move_method(
    src_abs: Path, project_dir: Path, dest_ignored: bool
) -> bool:
    """Determine if git should be used for the move operation.

    Args:
        src_abs: Absolute path to source
        project_dir: Project directory path
        dest_ignored: Whether .gitignore excludes the destination; such a
            destination is never committed, so git is not used.

    Returns:
        True if git should be used, False otherwise
    """
    if dest_ignored:
        return False

    # Lazy import: keeps GitPython off the common file-operation import path
    from mcp_workspace.git_operations import is_file_tracked, is_git_repository

    if not is_git_repository(project_dir):
        return False

    # Simply check if the source is tracked (for files)
    # For directories, git mv will handle it or fail gracefully
    if src_abs.is_file():
        return is_file_tracked(src_abs, project_dir)
    else:
        # For directories, just try git mv and let it fail if needed
        return True


def _execute_git_move(
    src_abs: Path, dest_abs: Path, src_rel: str, dest_rel: str, project_dir: Path
) -> dict[str, Any]:
    """Execute move using git mv.

    Args:
        src_abs: Absolute source path
        dest_abs: Absolute destination path
        src_rel: Relative source path
        dest_rel: Relative destination path
        project_dir: Project directory path

    Returns:
        Dict with move result

    Raises:
        Exception: If git move fails
    """
    # Lazy import: keeps GitPython off the common file-operation import path
    from mcp_workspace.git_operations import git_move as git_move_impl

    logger.info("Attempting git move: %s -> %s", src_rel, dest_rel)
    logger.debug("Moving %s to %s using git mv", src_rel, dest_rel)

    git_move_impl(src_abs, dest_abs, project_dir)

    logger.info("Successfully moved using git: %s -> %s", src_rel, dest_rel)

    return {
        "success": True,
        "method": "git",
        "source": src_rel,
        "destination": dest_rel,
        "message": "File moved using git mv (preserving history)",
    }


def _execute_filesystem_move(
    src_abs: Path, dest_abs: Path, src_rel: str, dest_rel: str, is_fallback: bool
) -> dict[str, Any]:
    """Execute move using filesystem operations.

    Args:
        src_abs: Absolute source path
        dest_abs: Absolute destination path
        src_rel: Relative source path
        dest_rel: Relative destination path
        is_fallback: Whether this is a fallback from git

    Returns:
        Dict with move result

    Raises:
        PermissionError: If lacking permissions
        Exception: For other move errors
    """
    logger.debug("Moving %s to %s using filesystem operations", src_rel, dest_rel)

    # Use shutil.move for both files and directories
    shutil.move(str(src_abs), str(dest_abs))

    message = "File moved using filesystem operations"
    if is_fallback:
        message += " (fallback from git)"

    logger.info("Successfully moved: %s -> %s", src_rel, dest_rel)

    return {
        "success": True,
        "method": "filesystem",
        "source": src_rel,
        "destination": dest_rel,
        "message": message,
    }


@log_function_call  # Automatic logging of parameters, timing, and exceptions
def move_file(
    source_path: str, destination_path: str, project_dir: Path
) -> dict[str, Any]:
    """Move or rename a file or directory.

    Automatically uses git mv if the file is tracked by git,
    otherwise uses standard filesystem operations. A destination excluded
    by .gitignore always gets a plain filesystem move, so a tracked file
    moved there ends up untracked.
    Always creates parent directories if they don't exist.

    Access rules are not checked here; the move_file tool runs
    ``check_tree_access`` first.

    Args:
        source_path: Source file/directory path (relative to project_dir)
        destination_path: Destination path (relative to project_dir)
        project_dir: Project directory path

    Returns:
        Dict containing:
            - success: bool indicating if the move succeeded
            - method: 'git' or 'filesystem' indicating method used
            - source: normalized source path
            - destination: normalized destination path
            - message: optional status message

    Raises:
        FileNotFoundError: If source doesn't exist
        FileExistsError: If destination already exists
        ValueError: If paths are invalid or outside project directory
        PermissionError: If lacking permissions for the operation
    """
    # Validate and normalize paths
    src_abs, src_rel, dest_abs, dest_rel = _validate_move_parameters(
        source_path, destination_path, project_dir
    )

    # Automatically create parent directories
    dest_parent = dest_abs.parent
    dest_parent.mkdir(parents=True, exist_ok=True)

    # Determine if git should be used
    dest_ignored = is_path_gitignored(dest_rel, project_dir)
    should_use_git = _determine_move_method(src_abs, project_dir, dest_ignored)

    # Try git move if applicable
    if should_use_git:
        try:
            return _execute_git_move(src_abs, dest_abs, src_rel, dest_rel, project_dir)
        except Exception as e:
            logger.warning(
                "Git move failed for %s, falling back to filesystem: %s", src_rel, e
            )
            # Fall through to filesystem move

    # Use filesystem operations (either as primary method or fallback)
    try:
        return _execute_filesystem_move(
            src_abs, dest_abs, src_rel, dest_rel, is_fallback=should_use_git
        )
    except PermissionError as e:
        logger.error("Permission denied moving %s to %s: %s", src_rel, dest_rel, e)
        raise
    except Exception as e:
        logger.error("Error moving %s to %s: %s", src_rel, dest_rel, e)
        raise
