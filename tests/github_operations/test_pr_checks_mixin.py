"""Tests for PullRequestManager.get_non_green_checks() method.

Tests the non-green check lookup using a mocked GitHub API. A local
``checks_env`` fixture builds the git repo and patches the token/Github client.
"""

import time
from pathlib import Path
from typing import Iterator, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.pr_checks_mixin import PERMISSION_ERROR_TEXT
from mcp_workspace.github_operations.pr_manager import PullRequestManager


def _status(context: str, state: str) -> MagicMock:
    """Build a mock commit status."""
    status = MagicMock()
    status.context = context
    status.state = state
    return status


def _run(name: str, status: str, conclusion: Optional[str] = None) -> MagicMock:
    """Build a mock check run (``name`` is a MagicMock kwarg, so set it after)."""
    run = MagicMock()
    run.name = name
    run.status = status
    run.conclusion = conclusion
    return run


def _set_checks(
    mock_repo: MagicMock, statuses: List[MagicMock], runs: List[MagicMock]
) -> MagicMock:
    """Configure mock_repo.get_commit to return the given statuses and runs."""
    commit = MagicMock()
    commit.get_combined_status.return_value.statuses = statuses
    commit.get_check_runs.return_value = runs
    mock_repo.get_commit.return_value = commit
    return commit


@pytest.mark.git_integration
class TestGetNonGreenChecks:
    """Tests for get_non_green_checks() method."""

    @pytest.fixture
    def checks_env(
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

    def test_check_runs_classification(
        self, checks_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """Passing conclusions excluded; failing and unfinished runs included."""
        manager, mock_repo = checks_env
        _set_checks(
            mock_repo,
            [],
            [
                _run("ok", "completed", "success"),
                _run("neutral", "completed", "neutral"),
                _run("skip", "completed", "skipped"),
                _run("lint", "completed", "failure"),
                _run("cancel", "completed", "cancelled"),
                _run("slow", "completed", "timed_out"),
                _run("gate", "completed", "action_required"),
                _run("build", "in_progress"),
                _run("deploy", "queued"),
            ],
        )

        names, error = manager.get_non_green_checks(1, head_sha="abc")

        assert error is None
        assert names == (
            "lint (failure)",
            "cancel (cancelled)",
            "slow (timed_out)",
            "gate (action_required)",
            "build (in_progress)",
            "deploy (queued)",
        )

    def test_statuses_classification(
        self, checks_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """Success statuses excluded; pending/failure/error included before runs."""
        manager, mock_repo = checks_env
        _set_checks(
            mock_repo,
            [
                _status("ci/ok", "success"),
                _status("codecov/patch", "pending"),
                _status("ci/fail", "failure"),
                _status("ci/err", "error"),
            ],
            [_run("lint", "completed", "failure")],
        )

        names, error = manager.get_non_green_checks(1, head_sha="abc")

        assert error is None
        assert names == (
            "codecov/patch (pending)",
            "ci/fail (failure)",
            "ci/err (error)",
            "lint (failure)",
        )

    def test_all_green(self, checks_env: Tuple[PullRequestManager, MagicMock]) -> None:
        """Everything green -> ((), None)."""
        manager, mock_repo = checks_env
        _set_checks(
            mock_repo,
            [_status("ci/ok", "success")],
            [_run("ok", "completed", "success")],
        )

        assert manager.get_non_green_checks(1, head_sha="abc") == ((), None)

    def test_head_sha_given_skips_get_pull(
        self, checks_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """head_sha given -> get_pull not called, get_commit uses that SHA."""
        manager, mock_repo = checks_env
        _set_checks(mock_repo, [], [])

        manager.get_non_green_checks(7, head_sha="deadbeef")

        mock_repo.get_pull.assert_not_called()
        mock_repo.get_commit.assert_called_once_with("deadbeef")

    def test_head_sha_none_resolves_from_pr(
        self, checks_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """head_sha=None -> SHA resolved from repo.get_pull(pr_number).head.sha."""
        manager, mock_repo = checks_env
        _set_checks(mock_repo, [], [])
        mock_repo.get_pull.return_value.head.sha = "cafe123"

        manager.get_non_green_checks(7)

        mock_repo.get_pull.assert_called_once_with(7)
        mock_repo.get_commit.assert_called_once_with("cafe123")

    def test_permission_error(
        self, checks_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """403 without rate-limit headers -> PERMISSION_ERROR_TEXT."""
        manager, mock_repo = checks_env
        commit = _set_checks(mock_repo, [], [])
        commit.get_check_runs.side_effect = GithubException(
            403, {"message": "Resource not accessible"}, headers={}
        )

        assert manager.get_non_green_checks(1, head_sha="abc") == (
            (),
            PERMISSION_ERROR_TEXT,
        )

    def test_rate_limit_error(
        self, checks_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """403 with X-RateLimit-Remaining: 0 -> rate-limit text with reset time."""
        manager, mock_repo = checks_env
        commit = _set_checks(mock_repo, [], [])
        reset = str(int(time.time()) + 600)
        commit.get_check_runs.side_effect = GithubException(
            403,
            {"message": "API rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": reset},
        )

        names, error = manager.get_non_green_checks(1, head_sha="abc")

        assert names == ()
        assert error is not None
        assert error.startswith("GitHub rate limit exhausted")
        assert "resets at" in error

    def test_server_error(
        self, checks_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """500 -> 'GitHub API error 500: boom'."""
        manager, mock_repo = checks_env
        commit = _set_checks(mock_repo, [], [])
        commit.get_combined_status.side_effect = GithubException(
            500, {"message": "boom"}
        )

        assert manager.get_non_green_checks(1, head_sha="abc") == (
            (),
            "GitHub API error 500: boom",
        )

    def test_network_error_during_iteration(
        self, checks_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """ConnectionError while iterating check runs -> network error text."""
        manager, mock_repo = checks_env
        commit = _set_checks(mock_repo, [], [])

        def _runs() -> Iterator[MagicMock]:
            yield _run("lint", "completed", "failure")
            raise ConnectionError("socket closed")

        commit.get_check_runs.return_value = _runs()

        assert manager.get_non_green_checks(1, head_sha="abc") == (
            (),
            "network error: ConnectionError",
        )

    def test_repository_not_accessible(
        self, checks_env: Tuple[PullRequestManager, MagicMock]
    ) -> None:
        """_get_repository() returning None -> error, no raise."""
        manager, _ = checks_env
        with patch.object(manager, "_get_repository", return_value=None):
            names, error = manager.get_non_green_checks(1, head_sha="abc")

        assert names == ()
        assert error
