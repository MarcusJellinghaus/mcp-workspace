"""File operations utilities."""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from mcp_workspace.file_tools.line_endings import target_newline
from mcp_workspace.file_tools.path_utils import normalize_line_endings, normalize_path
from mcp_workspace.utils.git_paths import is_path_in_git_dir

logger = logging.getLogger(__name__)

DEFAULT_READ_MAX_LINES = 2000


def _contains_git_dir_error(directory: Path, rel_path: str) -> ValueError | None:
    """Build the refusal for a directory holding a ``.git`` entry at any depth.

    Args:
        directory: Directory about to be deleted or moved as a whole.
        rel_path: The same directory relative to the project, for the message.

    Returns:
        The ValueError to raise, or None when the directory holds no ``.git``.
    """
    if any(is_path_in_git_dir(entry.name) for entry in directory.rglob("*")):
        return ValueError(
            f"Security error: Directory '{rel_path}' contains a git directory, "
            "which the file tools do not access."
        )
    return None


def read_file(
    file_path: str,
    project_dir: Path,
    start_line: int | None = None,
    end_line: int | None = None,
    with_line_numbers: bool | None = None,
    max_lines: int | None = None,
) -> str:
    """Read the contents of a file.

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
        max_lines: Maximum number of lines a full read returns. When the
            file is longer, the first *max_lines* lines are returned
            followed by a note naming the next range to read. ``None`` or
            ``0`` means no limit. Ignored for sliced reads.

    Returns:
        The contents of the file as a string

    Raises:
        FileNotFoundError: If the file does not exist
        IsADirectoryError: If the path is not a file
        PermissionError: If access to the file is denied
        ValueError: If the file is outside the project directory, if
            *start_line* / *end_line* are invalid, or if *max_lines* is
            negative or not an integer
    """
    # Validate file_path parameter
    if not file_path or not isinstance(file_path, str):
        logger.error("Invalid file path: %s", file_path)
        raise ValueError(f"File path must be a non-empty string, got {type(file_path)}")

    # Validate project_dir parameter
    if project_dir is None:
        raise ValueError("Project directory cannot be None")

    # Validate max_lines parameter
    if max_lines is not None:
        if isinstance(max_lines, bool) or not isinstance(max_lines, int):
            raise ValueError(f"max_lines must be an integer, got {type(max_lines)}")
        if max_lines < 0:
            raise ValueError(f"max_lines must be >= 0, got {max_lines}")

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

    try:
        logger.debug("Reading file: %s", rel_path)

        # Range reads are never limited
        limit = max_lines if (start_line is None and max_lines) else None
        total = 0
        collected: list[tuple[int, str]] = []
        with open(abs_path, encoding="utf-8") as file_handle:
            for line_num, line in enumerate(file_handle, start=1):
                if limit is not None and line_num > limit:
                    total = line_num  # count only; memory stays flat
                    continue
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

        if limit is not None and total > limit:
            content += (
                f"[truncated: showing lines 1–{limit} of {total}; "
                f"continue with start_line={limit + 1}, "
                f"end_line={min(2 * limit, total)}]"
            )

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


def _write_file_atomically(
    abs_path: Path, rel_path: str, content: str, newline: str
) -> bool:
    r"""Write file atomically using a temporary file.

    Args:
        abs_path: Absolute path to file
        rel_path: Relative path for logging
        content: LF-normalised content to write
        newline: Line ending each ``\n`` is written as

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
        with open(temp_fd, "w", encoding="utf-8", newline=newline) as f:
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
    """Write content to a file atomically.

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

    # Pick the ending before the write: Windows unlinks the target first
    existing = abs_path.read_bytes() if abs_path.is_file() else None
    newline = target_newline(existing, rel_path, project_dir)

    # Create parent directories if needed
    _create_parent_directories(abs_path)

    # Write file atomically
    return _write_file_atomically(abs_path, rel_path, validated_content, newline)


# Keep write_file for backward compatibility
write_file = save_file


def append_file(file_path: str, content: Any, project_dir: Path) -> bool:
    """Append content to the end of a file.

    Appends without touching existing bytes; the appended text uses the
    file's line ending (no line breaks → .gitattributes eol=, else platform
    default). No newline is inserted before it.

    Args:
        file_path: Path to the file to append to (relative to project directory)
        content: Content to append to the file
        project_dir: Project directory path

    Returns:
        True if the content was appended successfully

    Raises:
        FileNotFoundError: If the file does not exist
        IsADirectoryError: If the path is not a file
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

    newline = target_newline(abs_path.read_bytes(), rel_path, project_dir)

    logger.debug("Appending %s bytes to %s", len(validated_content), rel_path)
    with open(abs_path, "a", encoding="utf-8", newline=newline) as f:
        try:
            f.write(validated_content)
        except UnicodeEncodeError as e:
            logger.error(
                "Unicode encode error while appending to %s: %s", rel_path, str(e)
            )
            raise ValueError(
                "Content contains characters that cannot be encoded. Please check the encoding."
            ) from e
    return True


def delete_file(file_path: str, project_dir: Path) -> bool:
    """Delete a file.

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


def _format_deleted_paths(paths: list[str], n_files: int, n_dirs: int) -> list[str]:
    """Cap the deleted-path list at 20, appending a summary line as entry #21.

    Args:
        paths: The deleted paths (relative to project_dir) to cap.
        n_files: Total number of files deleted, used in the summary line.
        n_dirs: Total number of directories deleted, used in the summary line.

    Returns:
        The original path list unchanged when it holds 20 or fewer entries;
        otherwise the first 20 paths plus a summary line as entry #21.
    """
    # The 20-path cap is deliberate and has no lift parameter - unlike the read
    # tools, the deletion has already happened, so there is nothing to
    # re-request. The summary line carries the true file and directory totals.
    if len(paths) <= 20:
        return paths
    return paths[:20] + [
        f"... and {len(paths) - 20} more ({n_files} files, {n_dirs} dirs deleted total)"
    ]


def delete_directory(
    dir_path: str, project_dir: Path, recursive: bool = False
) -> list[str]:
    """Delete a directory (empty by default, whole tree with recursive=True).

    Plain filesystem — no git. Files-only tool is delete_file. Handles
    directories only. Missing directory is idempotent (no error).

    Args:
        dir_path: Path to the directory to delete (relative to project directory)
        project_dir: Project directory path
        recursive: If True, delete the directory tree via shutil.rmtree;
            otherwise only an empty directory is removed via Path.rmdir.

    Returns:
        List of deleted paths (relative to project_dir), capped at 20 entries
        with a summary line as entry #21 when more were deleted. A missing
        directory returns a single "does not exist" message.

    Raises:
        ValueError: If dir_path is invalid, project_dir is None, the path is
            outside the project directory, resolves to the project root, points
            to a file, the directory holds a .git entry at any depth, or it is
            non-empty without recursive=True.
    """
    # Validate dir_path parameter
    if not dir_path or not isinstance(dir_path, str):
        logger.error("Invalid directory path: %s", dir_path)
        raise ValueError(
            f"Directory path must be a non-empty string, got {type(dir_path)}"
        )

    # Validate project_dir parameter
    if project_dir is None:
        raise ValueError("Project directory cannot be None")

    # Normalize the path to be relative to the project directory
    abs_path, rel_path = normalize_path(dir_path, project_dir)

    # Refuse to delete the project root (would wipe the repo incl. .git)
    if abs_path.resolve() == project_dir.resolve():
        raise ValueError("Refusing to delete the project root directory")

    if not abs_path.exists():
        logger.debug("Directory not found (idempotent): %s", rel_path)
        return [f"Directory '{rel_path}' does not exist — nothing to delete"]

    if abs_path.is_file():
        logger.error("Path is a file, not a directory: %s", rel_path)
        raise ValueError(
            f"Path '{rel_path}' is a file, not a directory. "
            "Use delete_this_file instead."
        )

    # Single walk collected before deleting — paths vanish after rmtree.
    children = sorted(abs_path.rglob("*"))
    if children and not recursive:
        raise ValueError(
            f"Directory '{rel_path}' is not empty. "
            "Pass recursive=True to delete it and its contents."
        )

    git_dir_error = _contains_git_dir_error(abs_path, rel_path)
    if git_dir_error is not None:
        raise git_dir_error

    n_files = sum(1 for p in children if p.is_file())
    n_dirs = sum(1 for p in children if p.is_dir()) + 1
    all_rel = [rel_path] + [p.relative_to(project_dir).as_posix() for p in children]

    logger.debug("Deleting directory: %s (recursive=%s)", rel_path, recursive)
    if recursive:
        shutil.rmtree(abs_path)
    else:
        abs_path.rmdir()
    logger.debug("Successfully deleted directory: %s", rel_path)

    return _format_deleted_paths(all_rel, n_files, n_dirs)
