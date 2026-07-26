"""Selective file editing via exact string matching."""

import difflib
import logging
from pathlib import Path
from typing import Optional

from mcp_workspace.file_tools.path_utils import normalize_line_endings, normalize_path

logger = logging.getLogger(__name__)


def edit_file(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    project_dir: Optional[Path] = None,
) -> str:
    """Make a selective edit to a file using exact string matching.

    Args:
        file_path: Path to file (relative to project_dir if provided).
        old_string: Text to find and replace. Empty string inserts at beginning.
        new_string: Replacement text.
        replace_all: If True, replace all occurrences. If False and multiple
            matches exist, raises ValueError.
        project_dir: Base directory for relative paths.

    Returns:
        Diff string on success, or "No changes needed - edit already applied"
        if the edit was already applied.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If old_string is not found or matches multiple locations
            (when replace_all is False).
    """
    # Normalize backslashes so Windows-style paths resolve on POSIX too
    file_path = file_path.replace("\\", "/")

    # Resolve file path
    if project_dir:
        abs_path, _ = normalize_path(file_path, project_dir)
    else:
        abs_path = Path(file_path)

    if not abs_path.exists():
        raise FileNotFoundError(f"File not found: {abs_path}")

    if not abs_path.is_file():
        raise ValueError(f"Not a file: {abs_path}")

    # Read and normalize content
    with open(abs_path, "r", encoding="utf-8") as f:
        original_content = normalize_line_endings(f.read())

    old_string = normalize_line_endings(old_string)
    new_string = normalize_line_endings(new_string)

    # Empty old_string → prepend new_string
    if not old_string:
        modified_content = new_string + original_content
        _write_file(abs_path, modified_content)
        return _create_diff(original_content, modified_content, file_path)

    # Check if old_string exists in content
    if old_string in original_content:
        count = original_content.count(old_string)

        if count > 1 and not replace_all:
            raise ValueError(
                f"Multiple matches ({count}) found for {_truncate(old_string)}. "
                f"Use replace_all=True to replace all occurrences, or provide "
                f"more context to create a unique match."
            )

        # Position-aware already-applied check
        if _is_position_aware_already_applied(original_content, old_string, new_string):
            return "No changes needed - edit already applied"

        # Apply replacement
        if replace_all:
            modified_content = original_content.replace(old_string, new_string)
        else:
            modified_content = original_content.replace(old_string, new_string, 1)

        _write_file(abs_path, modified_content)
        return _create_diff(original_content, modified_content, file_path)

    # old_string not found — check contextual already-applied
    if _is_edit_already_applied(original_content, old_string, new_string):
        return "No changes needed - edit already applied"

    # Build error message with optional backslash hint
    doubled = old_string.replace("\\", "\\\\")
    if doubled != old_string and doubled in original_content:
        raise ValueError(
            f"Text not found: {_truncate(old_string)}\n"
            "Hint: file may store backslashes as `\\\\` (double backslashes)"
            " — use double backslashes in both `old_string` and `new_string`."
        )

    raise ValueError(f"Text not found in {abs_path}: {_truncate(old_string)}")


def _write_file(path: Path, content: str) -> None:
    """Write content to file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _is_position_aware_already_applied(
    content: str, old_string: str, new_string: str
) -> bool:
    """Check if edit is already applied using position-aware detection.

    When new_string is longer than old_string and old_string is a prefix of
    new_string, the old_string will still be found in content even after the
    edit is applied. This checks if the content at the match position already
    contains new_string.

    Returns:
        True if the content at the match position already contains new_string.
    """
    if len(new_string) <= len(old_string):
        return False

    pos = content.find(old_string)
    return content[pos : pos + len(new_string)] == new_string


def _truncate(text: str, max_len: int = 50) -> str:
    """Truncate text for error messages.

    Returns:
        The text unchanged if within max_len, otherwise truncated with "...".
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _create_diff(original: str, modified: str, filename: str) -> str:
    """Create unified diff between original and modified content.

    Returns:
        Unified diff as a single string.
    """
    filename = filename.replace("\\", "/")
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    return "".join(
        difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )


def _is_edit_already_applied(content: str, old_string: str, new_string: str) -> bool:
    """Check if an edit has already been applied by verifying contextual conditions.

    Returns:
        True if old_string is NOT found in content AND new_string IS found.
    """
    return old_string not in content and new_string in content
