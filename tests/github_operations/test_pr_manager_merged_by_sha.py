"""Tests for PullRequestManager.find_merged_pr_by_head_sha() method.

Tests merged-PR lookup by head commit SHA using mocked GitHub API.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.pr_manager import PullRequestManager

SHA = "a" * 40
OTHER_SHA = "b" * 40
MERGED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _make_pr(number: int, head_sha: str, merged_at: datetime | None) -> MagicMock:
    """Build a list-payload PR mock with only the fields the method reads."""
    pr = MagicMock()
    pr.number = number
    pr.head.sha = head_sha
    pr.merged_at = merged_at
    return pr


@pytest.fixture(name="mock_repo")
def fixture_mock_repo() -> Iterator[MagicMock]:
    """Patch the GitHub client so ``get_repo`` returns a fresh repository mock."""
    with patch("mcp_workspace.github_operations._client.Github") as mock_github:
        repo = MagicMock()
        mock_github.return_value.get_repo.return_value = repo
        yield repo


@pytest.fixture(name="manager")
def fixture_manager(tmp_path: Path) -> Iterator[PullRequestManager]:
    """PullRequestManager on a local repo with a GitHub origin."""
    git_dir = tmp_path / "git_dir"
    git_dir.mkdir()
    repo = git.Repo.init(git_dir)
    repo.create_remote("origin", "https://github.com/testowner/testrepo.git")
    with patch(
        "mcp_workspace.github_operations.base_manager.get_github_token",
        return_value="dummy-token",
    ):
        yield PullRequestManager(git_dir)


@pytest.mark.git_integration
class TestFindMergedPrByHeadSha:
    """Tests for find_merged_pr_by_head_sha() method."""

    def test_merged_pr_with_matching_head(
        self, manager: PullRequestManager, mock_repo: MagicMock
    ) -> None:
        """Merged PR whose head is the SHA → its number."""
        mock_repo.get_commit.return_value.get_pulls.return_value = [
            _make_pr(7, SHA, MERGED_AT)
        ]

        assert manager.find_merged_pr_by_head_sha(SHA) == 7
        mock_repo.get_commit.assert_called_once_with(SHA)

    def test_unmerged_pr_with_matching_head(
        self, manager: PullRequestManager, mock_repo: MagicMock
    ) -> None:
        """Matching head but ``merged_at`` is None → None."""
        mock_repo.get_commit.return_value.get_pulls.return_value = [
            _make_pr(7, SHA, None)
        ]

        assert manager.find_merged_pr_by_head_sha(SHA) is None

    def test_merged_pr_with_other_head(
        self, manager: PullRequestManager, mock_repo: MagicMock
    ) -> None:
        """Merged PR that merely contains the commit (different head) → None."""
        mock_repo.get_commit.return_value.get_pulls.return_value = [
            _make_pr(7, OTHER_SHA, MERGED_AT)
        ]

        assert manager.find_merged_pr_by_head_sha(SHA) is None

    def test_picks_matching_pr_among_several(
        self, manager: PullRequestManager, mock_repo: MagicMock
    ) -> None:
        """Only the merged PR whose head matches is returned."""
        mock_repo.get_commit.return_value.get_pulls.return_value = [
            _make_pr(5, OTHER_SHA, MERGED_AT),
            _make_pr(6, SHA, None),
            _make_pr(7, SHA, MERGED_AT),
        ]

        assert manager.find_merged_pr_by_head_sha(SHA) == 7

    def test_unknown_commit_422(
        self, manager: PullRequestManager, mock_repo: MagicMock
    ) -> None:
        """GithubException(422) from ``get_commit`` → None."""
        mock_repo.get_commit.side_effect = GithubException(
            422, {"message": "No commit found for SHA"}, None
        )

        assert manager.find_merged_pr_by_head_sha(SHA) is None

    @pytest.mark.parametrize("status", [404, 500, 502])
    def test_other_api_error_raised(
        self, manager: PullRequestManager, mock_repo: MagicMock, status: int
    ) -> None:
        """A non-422 API error is raised, not reported as "no merged PR"."""
        mock_repo.get_commit.side_effect = GithubException(
            status, {"message": "Server Error"}, None
        )

        with pytest.raises(GithubException):
            manager.find_merged_pr_by_head_sha(SHA)

    def test_network_error_raised(
        self, manager: PullRequestManager, mock_repo: MagicMock
    ) -> None:
        """A network error while listing PRs is raised."""
        mock_repo.get_commit.return_value.get_pulls.side_effect = ConnectionError(
            "connection reset"
        )

        with pytest.raises(ConnectionError):
            manager.find_merged_pr_by_head_sha(SHA)

    def test_inaccessible_repository_raised(self, manager: PullRequestManager) -> None:
        """A repository that cannot be fetched is an error, not "no merged PR"."""
        with patch.object(manager, "_get_repository", return_value=None):
            with pytest.raises(RuntimeError, match="cannot access"):
                manager.find_merged_pr_by_head_sha(SHA)

    def test_auth_error_401_raised(
        self, manager: PullRequestManager, mock_repo: MagicMock
    ) -> None:
        """GithubException(401) is re-raised to the caller."""
        mock_repo.get_commit.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )

        with pytest.raises(GithubException):
            manager.find_merged_pr_by_head_sha(SHA)

    @pytest.mark.parametrize(
        "sha",
        ["", "abc123", "g" * 40, "A" * 40, "a" * 39, "a" * 41, f"{'a' * 39}\n"],
    )
    def test_invalid_sha_no_api_call(
        self, manager: PullRequestManager, mock_repo: MagicMock, sha: str
    ) -> None:
        """Short, non-hex or uppercase SHA → None without any API call."""
        assert manager.find_merged_pr_by_head_sha(sha) is None
        mock_repo.get_commit.assert_not_called()
