"""Line-ending detection and selection for the file-writing tools."""

import logging
from pathlib import Path

from mcp_coder_utils.fs import count_line_endings, dominant_newline

logger = logging.getLogger(__name__)


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

    An existing file with line breaks keeps its dominant ending. A tie, no line
    breaks, or a new file follows ``.gitattributes`` ``eol=``, else LF.

    Args:
        existing: Current file content, or None for a new file
        rel_path: Path relative to project_dir
        project_dir: Project directory, or None to skip the gitattributes lookup

    Returns:
        ``"\n"``, ``"\r\n"`` or ``"\r"``
    """
    return dominant_newline(existing or b"") or _eol_from_gitattributes(
        rel_path, project_dir
    )


def _eol_from_gitattributes(rel_path: str, project_dir: Path | None) -> str:
    r"""Map ``eol=lf`` / ``eol=crlf`` to its newline; anything else to LF.

    Args:
        rel_path: Path relative to project_dir
        project_dir: Project directory, or None to skip the lookup (LF)

    Returns:
        ``"\n"`` or ``"\r\n"``
    """
    if project_dir is None:
        return "\n"
    try:
        # Lazy import: keeps GitPython off the common file-operation import path
        from mcp_workspace.git_operations import get_eol_attribute

        value = get_eol_attribute(rel_path, project_dir)
    except Exception as e:  # pylint: disable=broad-exception-caught  # git missing / not a repo / any git error -> LF
        logger.debug("No gitattributes eol for %s: %s", rel_path, e)
        return "\n"
    return {"lf": "\n", "crlf": "\r\n"}.get(value or "", "\n")
