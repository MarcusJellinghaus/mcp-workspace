"""Branch naming utilities for GitHub issues."""

import re
from typing import List, Optional, TypedDict


class BranchCreationResult(TypedDict):
    """TypedDict for branch creation result.

    Represents the result of a branch creation operation with all relevant fields.
    """

    success: bool
    branch_name: str
    error: Optional[str]
    existing_branches: List[str]


def generate_branch_name_from_issue(
    issue_number: int, issue_title: str, max_length: int = 200
) -> str:
    """Generate sanitized branch name matching GitHub's native rules.

    Args:
        issue_number: Issue number (e.g., 123)
        issue_title: Raw issue title (e.g., "Add New Feature - Part 1")
        max_length: Max branch name length in characters (default 200)

    Returns:
        Sanitized branch name (e.g., "123-add-new-feature---part-1")
    """
    # Step 1: Protect " - " separator with placeholder (GitHub-specific rule)
    # Use lowercase placeholder to avoid case conversion issues
    PROTECTED_SEPARATOR = "\x00sep\x00"
    sanitized = issue_title.replace(" - ", PROTECTED_SEPARATOR)

    # Step 2: Convert to lowercase
    sanitized = sanitized.lower()

    # Step 3: Replace non-alphanumeric (except dash and placeholder) with dash
    sanitized = re.sub(r"[^a-z0-9-\x00]+", "-", sanitized)

    # Step 4: Collapse multiple consecutive dashes to single dash
    sanitized = re.sub(r"-{2,}", "-", sanitized)

    # Step 5: Restore protected separators as "---"
    sanitized = sanitized.replace(PROTECTED_SEPARATOR, "---")

    # Step 6: Strip leading/trailing dashes
    sanitized = sanitized.strip("-")

    # Step 7: Truncate to max_length if needed
    branch_prefix = f"{issue_number}-"
    # An empty title leaves just the issue number
    full_branch_name = f"{branch_prefix}{sanitized}" if sanitized else str(issue_number)

    if len(full_branch_name) > max_length:
        # Keep issue number prefix and truncate title
        available_for_title = max_length - len(branch_prefix)
        if available_for_title > 0:
            truncated_title = sanitized[:available_for_title].rstrip("-")
            full_branch_name = f"{branch_prefix}{truncated_title}"
        else:
            # If even the prefix is too long, just return the issue number
            full_branch_name = str(issue_number)

    return full_branch_name
