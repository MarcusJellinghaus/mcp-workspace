"""Path utilities for file operations."""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def normalize_line_endings(text: str) -> str:
    r"""Convert all line endings to Unix style (\n).

    Returns:
        The text with CRLF and CR line endings converted to LF.
    """
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return text


def normalize_path(path: str, project_dir: Path) -> tuple[Path, str]:
    """Normalize a path to be relative to the project directory.

    Args:
        path: Path to normalize
        project_dir: Project directory path

    Returns:
        Tuple of (absolute path, relative path)

    Raises:
        ValueError: If the path is outside the project directory
    """
    if project_dir is None:
        raise ValueError("Project directory cannot be None")

    path_obj = Path(path)

    # If the path is absolute, make it relative to the project directory
    if path_obj.is_absolute():
        try:
            # Make sure the path is inside the project directory
            relative_path = path_obj.relative_to(project_dir)
            return path_obj, str(relative_path)
        except ValueError as exc:
            raise ValueError(
                f"Security error: Path '{path}' is outside the project directory '{project_dir}'. "
                f"All file operations must be within the project directory."
            ) from exc

    # If the path is already relative, make sure it doesn't try to escape
    absolute_path = project_dir / path_obj
    try:
        # Make sure the resolved path is inside the project directory
        # During testing, resolve() may fail on non-existent paths, so handle that case
        try:
            resolved_path = absolute_path.resolve()
            project_resolved = project_dir.resolve()
            # Check if the resolved path starts with the resolved project dir
            if os.path.commonpath([resolved_path, project_resolved]) != str(
                project_resolved
            ):
                raise ValueError(
                    f"Security error: Path '{path}' resolves to a location outside "
                    f"the project directory '{project_dir}'. Path traversal is not allowed."
                )
        except OSError:
            logger.warning(
                "Path.resolve() failed for '%s', using fallback check",
                absolute_path,
            )
            if ".." in absolute_path.parts:
                raise ValueError(
                    f"Security error: Path '{path}' contains '..' traversal."
                )

        return absolute_path, str(path_obj)
    except ValueError as e:
        # If the error already has our detailed message, pass it through
        if "Security error:" in str(e):
            raise
        # Otherwise add more context
        raise ValueError(
            f"Security error: Path '{path}' is outside the project directory '{project_dir}'. "
            f"All file operations must be within the project directory."
        ) from e
