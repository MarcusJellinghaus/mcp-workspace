"""Line-ending detection and selection for the file-writing tools."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Read at call time so tests can monkeypatch it
PLATFORM_NEWLINE: str = os.linesep


def count_line_endings(data: bytes) -> tuple[int, int, int]:
    """Count the line endings in raw bytes.

    Args:
        data: Raw file content

    Returns:
        (crlf, lone lf, lone cr) counts
    """
    crlf = data.count(b"\r\n")
    return crlf, data.count(b"\n") - crlf, data.count(b"\r") - crlf


def describe_line_endings(text: str) -> str:
    """Describe line count and style of a non-empty text.

    Only CR, LF and CRLF count as line breaks.

    Args:
        text: Non-empty text

    Returns:
        E.g. ``"488 lines, CRLF"``, ``"2 lines, mixed"`` or ``"1 line"``
    """
    data = text.encode("utf-8")
    crlf, lf, cr = count_line_endings(data)
    lines = crlf + lf + cr
    if data and not data.endswith((b"\n", b"\r")):
        lines += 1
    styles = [name for name, n in (("CRLF", crlf), ("LF", lf), ("CR", cr)) if n]
    description = f"{lines} line{'s' if lines != 1 else ''}"
    if len(styles) == 1:
        return f"{description}, {styles[0]}"
    if styles:
        return f"{description}, mixed"
    return description


def target_newline(
    existing: bytes | None, rel_path: str, project_dir: Path | None
) -> str:
    r"""Choose the line ending to write.

    The existing file's style wins; a mixed file gets its most common ending,
    a tie the platform default. A new file, or one without line breaks, follows
    ``.gitattributes`` ``eol=``, else the platform default.

    Args:
        existing: Current file content, or None for a new file
        rel_path: Path relative to project_dir
        project_dir: Project directory, or None to skip the gitattributes lookup

    Returns:
        ``"\n"``, ``"\r\n"`` or ``"\r"``
    """
    if existing:
        crlf, lf, cr = count_line_endings(existing)
        top = max(crlf, lf, cr)
        if top:
            winners = [
                nl for n, nl in ((crlf, "\r\n"), (lf, "\n"), (cr, "\r")) if n == top
            ]
            return winners[0] if len(winners) == 1 else PLATFORM_NEWLINE
    return _eol_from_gitattributes(rel_path, project_dir)


def _eol_from_gitattributes(rel_path: str, project_dir: Path | None) -> str:
    r"""Map ``eol=lf`` / ``eol=crlf`` to its newline; anything else to the platform default.

    Args:
        rel_path: Path relative to project_dir
        project_dir: Project directory, or None to skip the lookup

    Returns:
        ``"\n"``, ``"\r\n"`` or PLATFORM_NEWLINE
    """
    if project_dir is None:
        return PLATFORM_NEWLINE
    try:
        # Lazy import: keeps GitPython off the common file-operation import path
        from mcp_workspace.git_operations import get_eol_attribute

        value = get_eol_attribute(rel_path, project_dir)
    except Exception as e:  # pylint: disable=broad-exception-caught  # git missing / not a repo / any git error -> platform default
        logger.debug("No gitattributes eol for %s: %s", rel_path, e)
        return PLATFORM_NEWLINE
    return {"lf": "\n", "crlf": "\r\n"}.get(value or "", PLATFORM_NEWLINE)
