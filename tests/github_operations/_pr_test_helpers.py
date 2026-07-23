"""Shared helpers for PullRequestManager unit tests."""

from typing import Any
from unittest.mock import MagicMock


def create_mock_pr(**overrides: Any) -> MagicMock:
    """Create a mock PR object with common defaults."""
    mock_pr = MagicMock()
    mock_pr.number = overrides.get("number", 123)
    mock_pr.title = overrides.get("title", "Test PR")
    mock_pr.body = overrides.get("body", "Test description")
    mock_pr.state = overrides.get("state", "open")
    mock_pr.head.ref = overrides.get("head_ref", "feature-branch")
    mock_pr.base.ref = overrides.get("base_ref", "main")
    mock_pr.html_url = overrides.get(
        "url", f"https://github.com/test/repo/pull/{mock_pr.number}"
    )
    mock_pr.mergeable = overrides.get("mergeable", True)
    mock_pr.mergeable_state = overrides.get("mergeable_state", "clean")
    mock_pr.merged = overrides.get("merged", False)
    mock_pr.draft = overrides.get("draft", False)
    # Handle optional datetime fields
    if overrides.get("created_at") is None and "skip_dates" not in overrides:
        mock_pr.created_at.isoformat.return_value = "2023-01-01T00:00:00Z"
    elif overrides.get("created_at"):
        mock_pr.created_at.isoformat.return_value = overrides["created_at"]
    else:
        mock_pr.created_at = None
    if overrides.get("updated_at") is None and "skip_dates" not in overrides:
        mock_pr.updated_at.isoformat.return_value = "2023-01-01T00:00:00Z"
    elif overrides.get("updated_at"):
        mock_pr.updated_at.isoformat.return_value = overrides["updated_at"]
    else:
        mock_pr.updated_at = None
    # Handle user
    if overrides.get("user") is None and "skip_user" not in overrides:
        mock_pr.user.login = overrides.get("user_login", "testuser")
    else:
        mock_pr.user = overrides.get("user")
    # Handle assignees (list of NamedUser-like objects with .login).
    # Default [] keeps existing tests green (an unconfigured MagicMock
    # would not be iterable in [a.login for a in pr.assignees]).
    mock_pr.assignees = overrides.get("assignees", [])
    return mock_pr
