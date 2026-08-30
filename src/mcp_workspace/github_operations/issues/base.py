"""Validation helpers for issue operations.

This module provides standalone validation functions extracted from IssueManager
for use by the mixin classes and manager.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "validate_issue_number",
    "validate_issue_number_or_log",
    "validate_comment_id",
    "parse_base_branch",
]


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
    if not isinstance(issue_number, int) or issue_number <= 0:
        logger.error(
            f"Invalid issue number: {issue_number}. Must be a positive integer."
        )
        return False
    return True


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

    Looks for a markdown heading (any level) containing "Base Branch" (case-insensitive)
    and extracts the content until the next heading.

    Args:
        body: GitHub issue body text

    Returns:
        Branch name if found and valid, None if not specified or empty

    Raises:
        ValueError: If base branch section contains multiple lines (malformed input)

    Example:
        >>> parse_base_branch("### Base Branch\\n\\nfeature/v2\\n\\n### Description")
        'feature/v2'
        >>> parse_base_branch("### Description\\n\\nNo base branch")
        None
    """
    if not body:
        return None

    # Case-insensitive match for any heading level (# to ######) with "Base Branch"
    # MULTILINE flag for ^ to match line starts, DOTALL for . to match newlines
    pattern = r"^#{1,6}\s*base\s*branch\s*\n(.*?)(?=^#{1,6}\s|\Z)"
    match = re.search(pattern, body, re.MULTILINE | re.DOTALL | re.IGNORECASE)

    if not match:
        return None

    content = match.group(1).strip()

    if not content:
        return None

    # Check for multi-line content (malformed input)
    if "\n" in content:
        raise ValueError(
            f"Base branch section contains multiple lines (malformed): {content!r}"
        )

    return content
