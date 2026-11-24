"""Path utilities for file operations."""

import logging
import os
from pathlib import Path, PureWindowsPath

from mcp_coder_utils.fs import check_path_within

from mcp_workspace.utils.git_paths import is_path_in_git_dir

logger = logging.getLogger(__name__)


# Reason text for a path the OS refuses to resolve at all. Unvalidatable means
# rejected, so it is reported as a security error like any other escape.
_UNRESOLVABLE = "cannot be resolved and is rejected as potentially"


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


def git_dir_error(path: str) -> ValueError:
    """Build the refusal for a path that is a ``.git`` entry or below one.

    Args:
        path: The path as it was requested

    Returns:
        The ValueError to raise; its message names no rules file and gives no
        hint, since no rule can expose ``.git``.
    """
    return ValueError(
        f"Security error: Path '{path}' is inside a git directory, "
        "which the file tools do not access."
    )


def resolves_into_git_dir(path: Path, project_dir: Path) -> bool:
    """Check whether a path reaches a ``.git`` entry once the OS has resolved it.

    Covers what the spelling alone cannot show: links, and names the filesystem
    maps to ``.git``. Each existing ancestor is also compared with the project's
    ``.git`` by file identity, for names that ``resolve()`` does not rewrite.

    Args:
        path: Absolute path to check; it need not exist.
        project_dir: Project directory the path belongs to.

    Returns:
        True if the resolved path is a ``.git`` entry or below one. False if it
        resolves outside the project or cannot be resolved; ``normalize_path``
        decides those cases.
    """
    try:
        base = project_dir.resolve()
        relative = path.resolve().relative_to(base)
    except (OSError, ValueError):
        return False
    if is_path_in_git_dir(relative.as_posix()):
        return True

    git_dir = base / ".git"
    ancestor = base
    for part in relative.parts:
        ancestor = ancestor / part
        try:
            if os.path.samefile(ancestor, git_dir):
                return True
        except OSError:
            return False
    return False


def normalize_path(path: str, project_dir: Path) -> tuple[Path, str]:
    """Normalize a path to be relative to the project directory.

    Relative paths are anchored to the project directory; absolute paths are
    taken as given. Validation is the shared ``check_path_within`` (no '..'
    segment, no NUL byte, the resolved path stays inside the resolved project
    directory), then a lexical ``relative_to(project_dir)`` check, then the
    refusal of a path that is - or resolves to - a ``.git`` entry or below one.

    Resolution is used only to *decide*: the returned absolute path is the
    lexically joined one, so a symlink names the link rather than its target
    (callers unlink and move the link itself) and callers can still call
    ``relative_to(project_dir)`` on it.

    Only the requested path is checked for '..'; a project_dir that itself
    carries a '..' segment is the caller's own, already-trusted anchor.

    Known limitation: when the shared check raises OSError, validation falls
    back to the lexical ``relative_to`` check ('..' is still rejected before
    resolving). A symlink inside the project whose target is outside it is
    *not* detected on that branch. Symlink loops: on Python 3.13+ a loop takes
    the lexical fallback and is then treated as missing by the file operations;
    on 3.11/3.12 ``resolves_into_git_dir`` still raises RuntimeError.

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
            directory component, neither of which contains '..'. A path the OS
            refuses to resolve at all, such as one with an embedded NUL byte,
            is rejected the same way rather than surfacing a raw ValueError.
            Also if the path is a ``.git`` entry or below one.
    """  # noqa: DOC501 - _outside_error returns the documented ValueError
    if project_dir is None:
        raise ValueError("Project directory cannot be None")

    path_obj = Path(path)
    joined_path = path_obj if path_obj.is_absolute() else project_dir / path_obj

    try:
        # The raw path, not joined_path: project_dir may itself contain '..',
        # which the shared check would reject.
        check_path_within(path, project_dir)
    except ValueError as exc:
        raise ValueError(
            f"Security error: {exc}. Path traversal outside the project "
            f"directory '{project_dir}' is not allowed."
        ) from exc
    except OSError:
        # Resolution unavailable; '..' was rejected before resolving and the
        # relative_to below is the remaining check. A symlink escape is not
        # detected on this branch - see the docstring's known limitation.
        logger.warning(
            "Path.resolve() failed for '%s', using fallback check", joined_path
        )

    try:
        relative_path = joined_path.relative_to(project_dir)
    except ValueError as exc:
        raise _outside_error(path, project_dir, "is") from exc

    relative_posix = relative_path.as_posix()
    if is_path_in_git_dir(relative_posix) or resolves_into_git_dir(
        joined_path, project_dir
    ):
        raise git_dir_error(path)

    return joined_path, relative_posix


def _segments(path: str) -> list[str]:
    """Split a path on either separator, dropping empty and '.' segments.

    Returns:
        The meaningful segments in order.
    """
    return [x for x in path.replace("\\", "/").split("/") if x not in ("", ".")]


def _folded(segments: list[str]) -> list[str]:
    """Fold segments for comparison the way the local filesystem would.

    Returns:
        The segments casefolded on Windows, unchanged elsewhere.
    """
    if os.name == "nt":
        return [x.casefold() for x in segments]
    return segments


def ref_relative_path(path: str, root: Path) -> str:
    """Turn a caller's path into a repo-relative, forward-slash path for a tree lookup.

    Lexical only: nothing is resolved against the local checkout (``normalize_path``
    would resolve symlinks and reject paths that are valid upstream). An absolute
    path must start with the segments of ``root`` - resolved or as given - compared
    segment by segment, with empty and '.' segments dropped on both sides.

    Args:
        path: Path as the caller wrote it, relative to ``root`` or absolute.
        root: The reference project's directory.

    Returns:
        The relative path with forward slashes; "" for the root itself.

    Raises:
        ValueError: '..' segment, NUL byte, a .git entry under any spelling, or an
            absolute path outside ``root``.
    """  # noqa: DOC501 - _outside_error returns the documented ValueError
    if "\0" in path:
        raise _outside_error(path, root, _UNRESOLVABLE)

    parts = _segments(path)
    if ".." in parts:
        raise _outside_error(path, root, "contains '..' traversal and would escape")

    if PureWindowsPath(path).drive or path.replace("\\", "/").startswith("/"):
        folded_parts = _folded(parts)
        # Resolved first, then lexical: either spelling of the root is accepted.
        roots = [_segments(str(root.resolve())), _segments(str(root))]
        prefix = next(
            (r for r in roots if folded_parts[: len(r)] == _folded(r)),
            None,
        )
        if prefix is None:
            raise _outside_error(path, root, "resolves to a location")
        parts = parts[len(prefix) :]

    relative = "/".join(parts)
    if is_path_in_git_dir(relative):
        raise ValueError(
            f"Security error: Path '{path}' is inside a git directory, "
            "which the file tools do not access."
        )
    return relative
