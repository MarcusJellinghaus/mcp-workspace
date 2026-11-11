"""Tests for remote_head_sha."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git import Repo

from mcp_workspace.git_operations._subprocess_git import GitOutput
from mcp_workspace.git_operations.remotes import (
    push_current_branch,
    remote_head_sha,
)

from .conftest import commit_files

MODULE = "mcp_workspace.git_operations.remotes"

SHA = "0123456789abcdef0123456789abcdef01234567"


def _output(stdout: str) -> GitOutput:
    """Build a successful run_git_timed result."""
    return GitOutput(success=True, error=None, returncode=0, stderr="", stdout=stdout)


class TestRemoteHeadShaUnit:
    """remote_head_sha with run_git_timed mocked."""

    def test_matching_head(self, tmp_path: Path) -> None:
        """The SHA of the exact ref is returned."""
        run_mock = MagicMock(return_value=_output(f"{SHA}\trefs/heads/x\n"))

        with patch(f"{MODULE}.run_git_timed", run_mock):
            result = remote_head_sha(tmp_path, "x")

        run_mock.assert_called_once_with(
            tmp_path, "ls-remote", "--heads", "origin", "refs/heads/x"
        )
        assert result == {
            "success": True,
            "error": None,
            "returncode": 0,
            "stderr": "",
            "sha": SHA,
        }

    def test_suffix_match_ignored(self, tmp_path: Path) -> None:
        """``refs/heads/team/x`` does not answer for branch ``x``."""
        run_mock = MagicMock(return_value=_output(f"{SHA}\trefs/heads/team/x\n"))

        with patch(f"{MODULE}.run_git_timed", run_mock):
            result = remote_head_sha(tmp_path, "x")

        assert result["success"] is True
        assert result["sha"] is None

    def test_empty_output(self, tmp_path: Path) -> None:
        """No such branch on origin is a successful None."""
        with patch(f"{MODULE}.run_git_timed", return_value=_output("")):
            result = remote_head_sha(tmp_path, "x")

        assert result["success"] is True
        assert result["error"] is None
        assert result["sha"] is None

    def test_failure_passed_through(self, tmp_path: Path) -> None:
        """A failed ls-remote keeps error, returncode and stderr."""
        failed = GitOutput(
            success=False,
            error="git ls-remote failed (exit 128)",
            returncode=128,
            stderr="fatal: unreachable\n",
            stdout="",
        )

        with patch(f"{MODULE}.run_git_timed", return_value=failed):
            result = remote_head_sha(tmp_path, "x")

        assert result == {
            "success": False,
            "error": "git ls-remote failed (exit 128)",
            "returncode": 128,
            "stderr": "fatal: unreachable\n",
            "sha": None,
        }

    def test_timeout_passed_through(self, tmp_path: Path) -> None:
        """A timed-out ls-remote is a failure without a SHA."""
        timed_out = GitOutput(
            success=False,
            error="git ls-remote timed out after 120 s",
            returncode=None,
            stderr=None,
            stdout="",
        )

        with patch(f"{MODULE}.run_git_timed", return_value=timed_out):
            result = remote_head_sha(tmp_path, "x")

        assert result["success"] is False
        assert result["error"] == "git ls-remote timed out after 120 s"
        assert result["returncode"] is None
        assert result["sha"] is None

    @pytest.mark.parametrize("branch", ["-x", "", "  "])
    def test_invalid_branch(self, tmp_path: Path, branch: str) -> None:
        """An option-like or blank name is refused without running git."""
        with patch(f"{MODULE}.run_git_timed") as run_mock:
            result = remote_head_sha(tmp_path, branch)

        assert result == {
            "success": False,
            "error": "Invalid branch name",
            "returncode": None,
            "stderr": None,
            "sha": None,
        }
        run_mock.assert_not_called()


@pytest.mark.git_integration
class TestRemoteHeadShaIntegration:
    """remote_head_sha against a real bare origin."""

    def test_pushed_branch(self, origin_clone: Path) -> None:
        """A pushed branch reports the local tip."""
        repo = Repo(origin_clone)
        repo.git.checkout("-b", "feature")
        commit_files(repo, {"feature.txt": "one\n"}, "feature work")
        assert push_current_branch(origin_clone)["success"] is True

        result = remote_head_sha(origin_clone, "feature")

        assert result["success"] is True, result
        assert result["sha"] == repo.git.rev_parse("HEAD")

    def test_unknown_branch(self, origin_clone: Path) -> None:
        """A branch origin does not have is a successful None."""
        result = remote_head_sha(origin_clone, "no-such-branch")

        assert result["success"] is True, result
        assert result["sha"] is None
