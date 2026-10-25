"""Tests for PullRequestManager.update_pull_request() method.

Tests editing a pull request's title and/or body using mocked GitHub API.
"""

from pathlib import Path
from typing import Any, Iterator, Optional, Tuple
from unittest.mock import MagicMock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.pr_manager import PullRequestManager

from ._pr_test_helpers import create_mock_pr


@pytest.fixture
def manager_and_repo(tmp_path: Path) -> Iterator[Tuple[PullRequestManager, MagicMock]]:
    """Yield a PullRequestManager wired to a mocked GitHub repository."""
    git_dir = tmp_path / "git_dir"
    git_dir.mkdir()
    repo = git.Repo.init(git_dir)
    repo.create_remote("origin", "https://github.com/testowner/testrepo.git")

    mock_repo = MagicMock()
    with (
        patch("mcp_workspace.github_operations._client.Github") as mock_github,
        patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ),
    ):
        mock_github.return_value.get_repo.return_value = mock_repo
        yield PullRequestManager(git_dir), mock_repo


@pytest.mark.git_integration
class TestUpdatePullRequest:
    """Tests for update_pull_request() method."""

    @pytest.mark.parametrize(
        "title, body, expected_kwargs, expected_title, expected_body",
        [
            ("  New  ", None, {"title": "New"}, "New", "Test description"),
            (None, "New body", {"body": "New body"}, "Test PR", "New body"),
            (
                "New",
                "New body",
                {"title": "New", "body": "New body"},
                "New",
                "New body",
            ),
            (None, "", {"body": ""}, "Test PR", ""),
        ],
        ids=["title_only", "body_only", "both", "clear_body"],
    )
    def test_update_fields(
        self,
        manager_and_repo: Tuple[PullRequestManager, MagicMock],
        title: Optional[str],
        body: Optional[str],
        expected_kwargs: dict[str, Any],
        expected_title: str,
        expected_body: str,
    ) -> None:
        """Only supplied fields are edited; result reflects the re-fetched PR."""
        manager, mock_repo = manager_and_repo
        mock_pr = create_mock_pr(title=expected_title, body=expected_body)
        mock_repo.get_pull.return_value = mock_pr

        result = manager.update_pull_request(123, title=title, body=body)

        mock_pr.edit.assert_called_once_with(**expected_kwargs)
        assert mock_repo.get_pull.call_count == 2
        assert result["title"] == expected_title
        assert result["body"] == expected_body

    def test_update_neither_field(
        self, manager_and_repo: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """No fields — no edit, no re-fetch, returns current PR data."""
        manager, mock_repo = manager_and_repo
        mock_pr = create_mock_pr()
        mock_repo.get_pull.return_value = mock_pr

        result = manager.update_pull_request(123)

        mock_pr.edit.assert_not_called()
        assert mock_repo.get_pull.call_count == 1
        assert result["number"] == 123

    def test_update_blank_title_raises(
        self, manager_and_repo: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """Blank title — ValueError raised before any API call."""
        manager, mock_repo = manager_and_repo

        with pytest.raises(ValueError, match="cannot be empty"):
            manager.update_pull_request(123, title="   ")

        mock_repo.get_pull.assert_not_called()

    def test_update_invalid_pr_number(
        self, manager_and_repo: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """Invalid pr_number — returns empty dict, get_pull not called."""
        manager, mock_repo = manager_and_repo

        result = manager.update_pull_request(0, title="New")

        assert not result  # empty dict
        mock_repo.get_pull.assert_not_called()

    def test_update_api_error(
        self, manager_and_repo: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """GithubException — returns empty dict (decorator handles)."""
        manager, mock_repo = manager_and_repo
        mock_repo.get_pull.side_effect = GithubException(
            404, {"message": "Not Found"}, None
        )

        result = manager.update_pull_request(123, title="New")

        assert not result  # empty dict
