"""Tests for PullRequestManager.merge_pull_request() method.

Tests merging a pull request using a mocked GitHub API. A local ``manager``
fixture builds the git repo and patches the token/Github client so the
per-test boilerplate copied into sibling tests is not repeated here.
"""

from pathlib import Path
from typing import Iterator, Tuple
from unittest.mock import MagicMock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.pr_manager import PullRequestManager

from ._pr_test_helpers import create_mock_pr


@pytest.mark.git_integration
class TestMergePullRequest:
    """Tests for merge_pull_request() method."""

    @pytest.fixture
    def merge_env(
        self, tmp_path: Path
    ) -> Iterator[Tuple[PullRequestManager, MagicMock]]:
        """Build a git repo + patched manager, yielding (manager, mock_repo)."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testowner/testrepo.git")

        mock_repo = MagicMock()
        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo

        with (
            patch(
                "mcp_workspace.github_operations._client.Github",
                return_value=mock_github_client,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="dummy-token",
            ),
        ):
            manager = PullRequestManager(git_dir)
            yield manager, mock_repo

    def test_merge_success_squash(
        self, merge_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """200 — outcome='merged', sha set, only merge_method kwarg forwarded."""
        manager, mock_repo = merge_env
        mock_pr = create_mock_pr()
        merge_status = MagicMock()
        merge_status.sha = "abc123"
        merge_status.message = "Pull Request successfully merged"
        mock_pr.merge.return_value = merge_status
        mock_repo.get_pull.return_value = mock_pr

        result = manager.merge_pull_request(123)

        assert result["merged"] is True
        assert result["outcome"] == "merged"
        assert result["sha"] == "abc123"
        assert result["status"] == 200
        mock_pr.merge.assert_called_once_with(merge_method="squash")

    def test_merge_refused_405_not_merged(
        self, merge_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """405, re-fetched pr.merged is False -> outcome='refused', status=405."""
        manager, mock_repo = merge_env
        mock_pr = create_mock_pr(merged=False)
        mock_pr.merge.side_effect = GithubException(
            405, {"message": "not mergeable"}, None
        )
        refetched = create_mock_pr(merged=False)
        mock_repo.get_pull.side_effect = [mock_pr, refetched]

        result = manager.merge_pull_request(123)

        assert result["outcome"] == "refused"
        assert result["merged"] is False
        assert result["status"] == 405
        assert mock_repo.get_pull.call_count == 2

    def test_merge_405_refetch_merged_true(
        self, merge_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """405, re-fetched pr.merged is True -> outcome='merged', merge_commit_sha."""
        manager, mock_repo = merge_env
        mock_pr = create_mock_pr(merged=False)
        mock_pr.merge.side_effect = GithubException(
            405, {"message": "not mergeable"}, None
        )
        refetched = create_mock_pr(merged=True)
        refetched.merge_commit_sha = "deadbeef"
        mock_repo.get_pull.side_effect = [mock_pr, refetched]

        result = manager.merge_pull_request(123)

        assert result["outcome"] == "merged"
        assert result["merged"] is True
        assert result["sha"] == "deadbeef"
        assert result["status"] == 405

    def test_merge_405_refetch_fails(
        self, merge_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """405, second get_pull raises GithubException -> outcome='refused'."""
        manager, mock_repo = merge_env
        mock_pr = create_mock_pr(merged=False)
        mock_pr.merge.side_effect = GithubException(
            405, {"message": "not mergeable"}, None
        )
        mock_repo.get_pull.side_effect = [
            mock_pr,
            GithubException(500, {"message": "boom"}, None),
        ]

        result = manager.merge_pull_request(123)

        assert result["outcome"] == "refused"
        assert result["merged"] is False
        assert result["status"] == 405

    def test_merge_sha_mismatch_409(
        self, merge_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """409 (head moved) -> outcome='refused', status=409."""
        manager, mock_repo = merge_env
        mock_pr = create_mock_pr()
        mock_pr.merge.side_effect = GithubException(
            409, {"message": "head changed"}, None
        )
        mock_repo.get_pull.return_value = mock_pr

        result = manager.merge_pull_request(123, sha="oldsha")

        assert result["outcome"] == "refused"
        assert result["merged"] is False
        assert result["status"] == 409

    def test_merge_server_error_500(
        self, merge_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """500 -> outcome='error' (NOT refused)."""
        manager, mock_repo = merge_env
        mock_pr = create_mock_pr()
        mock_pr.merge.side_effect = GithubException(500, {"message": "boom"}, None)
        mock_repo.get_pull.return_value = mock_pr

        result = manager.merge_pull_request(123)

        assert result["outcome"] == "error"
        assert result["merged"] is False
        assert result["status"] == 500

    def test_merge_invalid_pr_number(
        self, merge_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """pr_number=0 -> outcome='error', get_pull not called."""
        manager, mock_repo = merge_env

        result = manager.merge_pull_request(0)

        assert result["outcome"] == "error"
        assert result["merged"] is False
        mock_repo.get_pull.assert_not_called()

    def test_merge_invalid_merge_method(
        self, merge_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """Invalid merge_method -> ValueError; get_pull not called."""
        manager, mock_repo = merge_env

        with pytest.raises(ValueError):
            manager.merge_pull_request(123, merge_method="fast-forward")

        mock_repo.get_pull.assert_not_called()

    def test_merge_auth_401_reraised(
        self, merge_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """401 -> GithubException bubbles up (config error, not an outcome)."""
        manager, mock_repo = merge_env
        mock_pr = create_mock_pr()
        mock_pr.merge.side_effect = GithubException(401, {"message": "bad creds"}, None)
        mock_repo.get_pull.return_value = mock_pr

        with pytest.raises(GithubException):
            manager.merge_pull_request(123)

    def test_merge_auth_403_reraised(
        self, merge_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """403 -> GithubException bubbles up (config error, not an outcome)."""
        manager, mock_repo = merge_env
        mock_pr = create_mock_pr()
        mock_pr.merge.side_effect = GithubException(403, {"message": "forbidden"}, None)
        mock_repo.get_pull.return_value = mock_pr

        with pytest.raises(GithubException):
            manager.merge_pull_request(123)

    def test_merge_passes_optional_kwargs(
        self, merge_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """Non-None sha/title/message are forwarded to pr.merge()."""
        manager, mock_repo = merge_env
        mock_pr = create_mock_pr()
        merge_status = MagicMock()
        merge_status.sha = "abc"
        merge_status.message = "merged"
        mock_pr.merge.return_value = merge_status
        mock_repo.get_pull.return_value = mock_pr

        result = manager.merge_pull_request(
            123,
            merge_method="merge",
            sha="s",
            commit_title="t",
            commit_message="m",
        )

        mock_pr.merge.assert_called_once_with(
            merge_method="merge",
            sha="s",
            commit_title="t",
            commit_message="m",
        )
        assert result["outcome"] == "merged"
