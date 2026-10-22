"""Shared helpers for issue-fetching unit tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import git

from mcp_workspace.github_operations.issues import IssueManager


@contextmanager
def real_issue_manager(tmp_path: Path) -> Iterator[IssueManager]:
    """Yield a real IssueManager whose ``_repository`` is a test/repo mock."""
    git_dir = tmp_path / "issue_manager_repo"
    git_dir.mkdir()
    git.Repo.init(git_dir).create_remote("origin", "https://github.com/test/repo.git")
    with (
        patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="test-token",
        ),
        patch("mcp_workspace.github_operations.base_manager.Github") as mock_github,
    ):
        mock_repo = Mock()
        mock_repo.full_name = "test/repo"
        mock_github.return_value.get_repo.return_value = mock_repo
        manager = IssueManager(git_dir)
        manager._repository = mock_repo
        yield manager


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
