"""Validation helpers for issue operations.

This module provides standalone validation functions extracted from IssueManager
for use by the mixin classes and manager.
"""

import logging
import re
from typing import Optional

from markdown_it import MarkdownIt

logger = logging.getLogger(__name__)

_MARKDOWN = MarkdownIt("commonmark")
_BASE_BRANCH_HEADING = re.compile(r"base\s*branch", re.IGNORECASE)
# markdown-it's own newline normalisation; str.splitlines() would also split on
# \x0b, \x0c, U+2028 ... and shift token.map line indices.
_LINE_BREAK = re.compile(r"\r\n|\r|\n")

__all__ = [
    "validate_issue_number",
    "validate_issue_number_or_log",
    "validate_comment_id",
    "parse_base_branch",
    "MalformedBaseBranchError",
    "format_malformed_base_branch",
]


class MalformedBaseBranchError(ValueError):
    """Raised when a Base Branch section in an issue body spans multiple lines."""

    def __init__(self, content: str) -> None:
        self.content = content
        super().__init__(
            f"Base branch section contains multiple lines (malformed): {content!r}"
        )


def format_malformed_base_branch(error: MalformedBaseBranchError) -> str:
    """Return the ready-to-show sentence for a malformed Base Branch section.

    Args:
        error: The error raised by parse_base_branch

    Returns:
        The bare sentence naming the problem, the fix, and the section's first
        line; callers add their own prefix (e.g. ``Error:``).
    """
    first_line = error.content.splitlines()[0]
    return (
        "`### Base Branch` must contain only the branch name on one line; "
        f"move other text to another section. First line: {first_line!r}"
    )


def validate_issue_number(issue_number: int) -> bool:
    """Validate issue number.

    Args:
        issue_number: Issue number to validate

    Returns:
        True if valid

    Raises:
        ValueError: If issue number is invalid
    """
    if not isinstance(issue_number, int) or issue_number <= 0:
        raise ValueError("Issue number must be a positive integer")
    return True


def validate_issue_number_or_log(issue_number: int) -> bool:
    """Validate issue number, logging instead of raising when it is invalid.

    Args:
        issue_number: Issue number to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        return validate_issue_number(issue_number)
    except ValueError:
        logger.error(
            f"Invalid issue number: {issue_number}. Must be a positive integer."
        )
        return False


def validate_comment_id(comment_id: int) -> bool:
    """Validate comment ID.

    Args:
        comment_id: Comment ID to validate

    Returns:
        True if valid

    Raises:
        ValueError: If comment ID is invalid
    """
    if not isinstance(comment_id, int) or comment_id <= 0:
        raise ValueError("Comment ID must be a positive integer")
    return True


def parse_base_branch(body: str) -> Optional[str]:
    r"""Parse base branch from issue body.

    Looks for a top-level ATX heading (``#`` to ``######``) reading "Base Branch"
    (case-insensitive) and extracts the raw content until the next top-level ATX
    heading of any level. Headings inside fenced code blocks, blockquotes, list
    items or HTML comments are ignored. The first matching section wins.

    Args:
        body: GitHub issue body text

    Returns:
        Branch name if found and valid, None if not specified or empty

    Raises:
        MalformedBaseBranchError: If base branch section contains multiple lines
            (malformed input). Subclasses ValueError.

    Example:
        >>> parse_base_branch("### Base Branch\\n\\nfeature/v2\\n\\n### Description")
        'feature/v2'
        >>> parse_base_branch("### Description\\n\\nNo base branch")
        None
    """
    if not body:
        return None

    tokens = _MARKDOWN.parse(body)
    lines = _LINE_BREAK.split(body)

    # Top-level ATX headings only: level 0 excludes blockquotes and list items,
    # "#" markup excludes setext headings.
    headings = [
        (index, token)
        for index, token in enumerate(tokens)
        if token.type == "heading_open"
        and token.level == 0
        and token.markup.startswith("#")
    ]

    for position, (index, token) in enumerate(headings):
        if not _BASE_BRANCH_HEADING.fullmatch(tokens[index + 1].content.strip()):
            continue
        assert token.map is not None
        if position + 1 < len(headings):
            next_map = headings[position + 1][1].map
            assert next_map is not None
            end = next_map[0]
        else:
            end = len(lines)
        content = "\n".join(lines[token.map[1] : end]).strip()

        if not content:
            return None

        # Check for multi-line content (malformed input)
        if "\n" in content:
            raise MalformedBaseBranchError(content)

        return content

    return None
