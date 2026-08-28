"""Shared helpers for issue-fetching unit tests."""

from unittest.mock import MagicMock


def make_mock_issue(number: int = 1, repo_full_name: str = "test/repo") -> MagicMock:
    """Create a mock issue whose identity satisfies _get_issue_checked."""
    mock_issue = MagicMock()
    mock_issue.number = number
    mock_issue.repository_url = f"https://api.github.com/repos/{repo_full_name}"
    return mock_issue
