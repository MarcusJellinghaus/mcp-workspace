"""Shared helpers for issue-fetching unit tests."""

from unittest.mock import MagicMock, Mock

from mcp_workspace.github_operations.issues import IssueManager


def make_issue_manager() -> IssueManager:
    """Return an IssueManager for test/repo whose ``_repository`` is a mock.

    Built in repo_url mode, so no git repository or git process is needed.
    The owner/repo must stay ``test/repo``: ``make_mock_issue``'s
    ``repository_url`` identity check depends on it.
    """
    manager = IssueManager(
        repo_url="https://github.com/test/repo.git", github_token="test-token"
    )
    mock_repo = Mock()
    mock_repo.full_name = "test/repo"
    manager._repository = mock_repo
    return manager


def make_mock_issue(number: int = 1, repo_full_name: str = "test/repo") -> MagicMock:
    """Create a mock issue whose identity satisfies _get_issue_checked."""
    mock_issue = MagicMock()
    mock_issue.number = number
    mock_issue.repository_url = f"https://api.github.com/repos/{repo_full_name}"
    mock_issue.author_association = "OWNER"
    return mock_issue


def make_untrusted_issue(number: int, body: str, login: str = "mallory") -> MagicMock:
    """Create a non-PR mock issue by an author with association NONE."""
    mock_issue = make_mock_issue(number)
    mock_issue.body = body
    mock_issue.pull_request = None
    mock_issue.author_association = "NONE"
    mock_issue.user.login = login
    return mock_issue
