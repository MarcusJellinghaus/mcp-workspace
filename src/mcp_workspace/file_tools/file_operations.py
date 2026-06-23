"""File operations utilities."""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_coder_utils.log_utils import log_function_call

from mcp_workspace.file_tools.path_utils import normalize_line_endings, normalize_path

logger = logging.getLogger(__name__)


def read_file(
    file_path: str,
    project_dir: Path,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    with_line_numbers: Optional[bool] = None,
) -> str:
    """
    Read the contents of a file.

    Args:
        file_path: Path to the file to read (relative to project directory)
        project_dir: Project directory path
        start_line: First line to return (1-based, inclusive). Must be
            provided together with *end_line*.
        end_line: Last line to return (1-based, inclusive). Must be
            provided together with *start_line*.
        with_line_numbers: If ``True``, prefix each returned line with its
            line number.  Defaults to ``False`` for full reads and ``True``
            for sliced reads.

    Returns:
        The contents of the file as a string

    Raises:
        FileNotFoundError: If the file does not exist
        PermissionError: If access to the file is denied
        ValueError: If the file is outside the project directory, or if
            *start_line* / *end_line* are invalid
    """
    # Validate file_path parameter
    if not file_path or not isinstance(file_path, str):
        logger.error("Invalid file path: %s", file_path)
        raise ValueError(f"File path must be a non-empty string, got {type(file_path)}")

    # Validate project_dir parameter
    if project_dir is None:
        raise ValueError("Project directory cannot be None")

    # --- Validate line-range parameters ---
    _has_start = start_line is not None
    _has_end = end_line is not None
    if _has_start != _has_end:
        raise ValueError(
            "start_line and end_line must both be provided or both omitted"
        )
    if _has_start:  # both are not None
        if not isinstance(start_line, int) or not isinstance(end_line, int):
            raise ValueError("start_line and end_line must be integers")
        if start_line < 1 or end_line < 1:
            raise ValueError("start_line and end_line must be >= 1")
        if end_line < start_line:
            raise ValueError(
                f"end_line ({end_line}) must be >= start_line ({start_line})"
            )

    # Normalize the path to be relative to the project directory
    abs_path, rel_path = normalize_path(file_path, project_dir)

    if not abs_path.exists():
        logger.error("File not found: %s", file_path)
        raise FileNotFoundError(f"File '{file_path}' does not exist")

    if not abs_path.is_file():
        logger.error("Path is not a file: %s", file_path)
        raise IsADirectoryError(f"Path '{file_path}' is not a file")

    file_handle = None
    try:
        logger.debug("Reading file: %s", rel_path)
        file_handle = open(abs_path, "r", encoding="utf-8")

        collected: list[tuple[int, str]] = []
        for line_num, line in enumerate(file_handle, start=1):
            if start_line is None or (start_line <= line_num <= end_line):  # type: ignore[operator]
                collected.append((line_num, line))
            if end_line is not None and line_num >= end_line:
                break

        # Resolve with_line_numbers default
        if with_line_numbers is None:
            with_line_numbers = start_line is not None

        if not with_line_numbers or not collected:
            content = "".join(line for _, line in collected)
        else:
            width = len(str(collected[-1][0]))
            content = "".join(f"{num:>{width}}→{line}" for num, line in collected)

        if start_line is not None:
            logger.debug("Read lines %d-%d from %s", start_line, end_line, rel_path)
        else:
            logger.debug("Successfully read %s", rel_path)

        return content
    except UnicodeDecodeError as e:
        logger.error("Unicode decode error while reading %s: %s", rel_path, str(e))
        raise ValueError(
            f"File '{file_path}' contains invalid characters. Ensure it's a valid text file."
        ) from e
    except Exception as e:
        logger.error("Error reading file %s: %s", rel_path, str(e))
        raise
    finally:
        if file_handle is not None:
            file_handle.close()


def _validate_save_parameters(
    file_path: str, content: Any, project_dir: Path
) -> tuple[Path, str, str]:
    """Validate and normalize save operation parameters.

    Args:
        file_path: Path to file (relative to project_dir)
        content: Content to write to file
        project_dir: Project directory path

    Returns:
        Tuple of (abs_path, rel_path, validated_content)

    Raises:
        ValueError: If parameters are invalid
    """
    # Validate file_path parameter
    if not file_path or not isinstance(file_path, str):
        logger.error("Invalid file path: %s", file_path)
        raise ValueError(f"File path must be a non-empty string, got {type(file_path)}")

    # Validate content parameter
    if content is None:
        logger.warning("Content is None, treating as empty string")
        content = ""
    elif not isinstance(content, str):
        logger.error("Invalid content type: %s", type(content))
        raise ValueError(f"Content must be a string, got {type(content)}")

    # Validate project_dir parameter
    if project_dir is None:
        raise ValueError("Project directory cannot be None")

    # Normalize the path to be relative to the project directory
    abs_path, rel_path = normalize_path(file_path, project_dir)

    content = normalize_line_endings(content)
    return abs_path, rel_path, content


def _create_parent_directories(abs_path: Path) -> None:
    """Create parent directories if they don't exist.

    Args:
        abs_path: Absolute path to file

    Raises:
        PermissionError: If lacking permissions to create directories
        Exception: For other directory creation errors
    """
    try:
        if not abs_path.parent.exists():
            logger.info("Creating directory: %s", abs_path.parent)
            abs_path.parent.mkdir(parents=True)
    except PermissionError as e:
        logger.error(
            "Permission denied creating directory %s: %s", abs_path.parent, str(e)
        )
        raise
    except Exception as e:
        logger.error("Error creating directory %s: %s", abs_path.parent, str(e))
        raise


def _write_file_atomically(abs_path: Path, rel_path: str, content: str) -> bool:
    """Write file atomically using a temporary file.

    Args:
        abs_path: Absolute path to file
        rel_path: Relative path for logging
        content: Content to write

    Returns:
        True if successful

    Raises:
        ValueError: If content cannot be encoded
        Exception: For other write errors
    """
    # Use a temporary file for atomic write
    temp_file = None
    try:
        # Create a temporary file in the same directory as the target
        # This ensures the atomic move works across filesystems
        temp_fd, temp_path = tempfile.mkstemp(dir=str(abs_path.parent))
        temp_file = Path(temp_path)

        logger.debug("Writing to temporary file for %s", rel_path)

        # Write content to temporary file
        with open(temp_fd, "w", encoding="utf-8") as f:
            try:
                f.write(content)
            except UnicodeEncodeError as e:
                logger.error(
                    "Unicode encode error while writing to %s: %s", rel_path, str(e)
                )
                raise ValueError(
                    "Content contains characters that cannot be encoded. Please check the encoding."
                ) from e

        # Atomically replace the target file
        logger.debug("Atomically replacing %s with temporary file", rel_path)
        try:
            # On Windows, we need to remove the target file first
            if os.name == "nt" and abs_path.exists():
                abs_path.unlink()
            os.replace(temp_path, str(abs_path))
        except Exception as e:
            logger.error("Error replacing file %s: %s", rel_path, str(e))
            raise

        logger.debug("Successfully wrote %s bytes to %s", len(content), rel_path)
        return True

    finally:
        # Clean up the temporary file if it still exists
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
            except Exception as e:
                logger.warning(
                    "Failed to clean up temporary file %s: %s", temp_file, str(e)
                )


def save_file(file_path: str, content: Any, project_dir: Path) -> bool:
    """
    Write content to a file atomically.

    Args:
        file_path: Path to the file to write to (relative to project directory)
        content: Content to write to the file
        project_dir: Project directory path

    Returns:
        True if the file was written successfully

    Raises:
        PermissionError: If access to the file is denied
        ValueError: If the file is outside the project directory
    """
    # Validate and normalize parameters
    abs_path, rel_path, validated_content = _validate_save_parameters(
        file_path, content, project_dir
    )

    # Create parent directories if needed
    _create_parent_directories(abs_path)

    # Write file atomically
    return _write_file_atomically(abs_path, rel_path, validated_content)


# Keep write_file for backward compatibility
write_file = save_file


def append_file(file_path: str, content: Any, project_dir: Path) -> bool:
    """
    Append content to the end of a file.

    Args:
        file_path: Path to the file to append to (relative to project directory)
        content: Content to append to the file
        project_dir: Project directory path

    Returns:
        True if the content was appended successfully

    Raises:
        FileNotFoundError: If the file does not exist
        PermissionError: If access to the file is denied
        ValueError: If the file is outside the project directory
    """
    abs_path, rel_path, validated_content = _validate_save_parameters(
        file_path, content, project_dir
    )

    # Check if the file exists
    if not abs_path.exists():
        logger.error("File not found: %s", file_path)
        raise FileNotFoundError(f"File '{file_path}' does not exist")

    if not abs_path.is_file():
        logger.error("Path is not a file: %s", file_path)
        raise IsADirectoryError(f"Path '{file_path}' is not a file")

    # Read existing content
    existing_content = read_file(file_path, project_dir)

    # Append new content
    combined_content = existing_content + validated_content

    # Use save_file to write the combined content
    logger.debug("Appending %s bytes to %s", len(validated_content), rel_path)
    return save_file(file_path, combined_content, project_dir)


def delete_file(file_path: str, project_dir: Path) -> bool:
    """
    Delete a file.

    Args:
        file_path: Path to the file to delete (relative to project directory)
        project_dir: Project directory path

    Returns:
        True if the file was deleted successfully

    Raises:
        FileNotFoundError: If the file does not exist
        PermissionError: If access to the file is denied
        IsADirectoryError: If the path points to a directory
        ValueError: If the file is outside the project directory or the parameter is invalid
    """
    # Validate file_path parameter
    if not file_path or not isinstance(file_path, str):
        logger.error("Invalid file path: %s", file_path)
        raise ValueError(f"File path must be a non-empty string, got {type(file_path)}")

    # Validate project_dir parameter
    if project_dir is None:
        raise ValueError("Project directory cannot be None")

    # Normalize the path to be relative to the project directory
    abs_path, rel_path = normalize_path(file_path, project_dir)

    if not abs_path.exists():
        logger.error("File not found: %s", file_path)
        raise FileNotFoundError(f"File '{file_path}' does not exist")

    if not abs_path.is_file():
        logger.error("Path is not a file: %s", file_path)
        raise IsADirectoryError(f"Path '{file_path}' is not a file or is a directory")

    try:
        logger.debug("Deleting file: %s", rel_path)
        abs_path.unlink()
        logger.debug("Successfully deleted file: %s", rel_path)
        return True
    except PermissionError as e:
        logger.error("Permission denied when deleting file %s: %s", rel_path, str(e))
        raise
    except Exception as e:
        logger.error("Error deleting file %s: %s", rel_path, str(e))
        raise


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
        ValueError: If paths are invalid
        FileNotFoundError: If source doesn't exist
        FileExistsError: If destination already exists
    """
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

    # Check if destination already exists
    if dest_abs.exists():
        raise FileExistsError(f"Destination '{destination_path}' already exists")

    return src_abs, src_rel, dest_abs, dest_rel


def _determine_move_method(src_abs: Path, project_dir: Path) -> bool:
    """Determine if git should be used for the move operation.

    Args:
        src_abs: Absolute path to source
        project_dir: Project directory path

    Returns:
        True if git should be used, False otherwise
    """
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
) -> Dict[str, Any]:
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
) -> Dict[str, Any]:
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
) -> Dict[str, Any]:
    """
    Move or rename a file or directory.

    Automatically uses git mv if the file is tracked by git,
    otherwise uses standard filesystem operations.
    Always creates parent directories if they don't exist.

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
    should_use_git = _determine_move_method(src_abs, project_dir)

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
