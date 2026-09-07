"""Path utilities for file operations."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def normalize_line_endings(text: str) -> str:
    r"""Convert all line endings to Unix style (\n).

    Returns:
        The text with CRLF and CR line endings converted to LF.
    """
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return text


def _outside_error(path: str, project_dir: Path, reason: str) -> ValueError:
    """Build the error for a path that leaves the project directory.

    Args:
        path: The path as it was requested
        project_dir: Project directory the path had to stay within
        reason: How the path leaves the directory, e.g. "resolves to a location"

    Returns:
        The ValueError to raise; its message always carries both "traversal"
        and "outside the project directory".
    """
    return ValueError(
        f"Security error: Path '{path}' {reason} outside the project directory "
        f"'{project_dir}'. Path traversal is not allowed."
    )


def normalize_path(path: str, project_dir: Path) -> tuple[Path, str]:
    """Normalize a path to be relative to the project directory.

    Relative paths are anchored to the project directory; absolute paths are
    taken as given. The result is validated twice: no '..' segment anywhere,
    and the resolved path stays inside the resolved project directory.

    Resolution is used only to *decide*: the returned absolute path is the
    lexically joined one, so a symlink names the link rather than its target
    (callers unlink and move the link itself) and callers can still call
    ``relative_to(project_dir)`` on it.

    Args:
        path: Path to normalize
        project_dir: Project directory path

    Returns:
        Tuple of (absolute path, relative path)

    Raises:
        ValueError: If the path is outside the project directory. This includes
            a '..' segment anywhere in the path, mid-path ones such as
            "src/../README.md" included, and a path that resolves outside the
            project through a symlink - either a symlinked file or a symlinked
            directory component, neither of which contains '..'.
    """  # noqa: DOC501 - _outside_error returns the documented ValueError
    if project_dir is None:
        raise ValueError("Project directory cannot be None")

    path_obj = Path(path)
    joined_path = path_obj if path_obj.is_absolute() else project_dir / path_obj

    if ".." in joined_path.parts:
        raise _outside_error(
            path, project_dir, "contains '..' traversal and would escape"
        )

    try:
        # Both resolve() calls belong in the same try: either may fail.
        if not joined_path.resolve().is_relative_to(project_dir.resolve()):
            raise _outside_error(path, project_dir, "resolves to a location")
    except OSError:
        # Resolution unavailable; the '..' guard above and the relative_to
        # below carry the validation between them.
        logger.warning(
            "Path.resolve() failed for '%s', using fallback check", joined_path
        )

    try:
        relative_path = joined_path.relative_to(project_dir)
    except ValueError as exc:
        raise _outside_error(path, project_dir, "is") from exc

    return joined_path, str(relative_path)
