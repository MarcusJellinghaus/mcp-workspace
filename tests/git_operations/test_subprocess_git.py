"""Tests for the timeout-bounded git subprocess helper."""

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from git import Repo

from mcp_workspace.git_operations._subprocess_git import (
    GIT_NETWORK_TIMEOUT,
    run_git_timed,
)

MODULE = "mcp_workspace.git_operations._subprocess_git"
GIT_PATH = "/usr/bin/git"


def _completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> "subprocess.CompletedProcess[str]":
    """Build a completed git process with the given outputs."""
    return subprocess.CompletedProcess(
        args=[GIT_PATH], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _run_patched(tmp_path: Path, run_mock: MagicMock, *args: str, **kwargs: Any) -> Any:
    """Call run_git_timed with git found on PATH and subprocess.run mocked."""
    with (
        patch(f"{MODULE}.shutil.which", return_value=GIT_PATH),
        patch(f"{MODULE}.subprocess.run", run_mock),
    ):
        return run_git_timed(tmp_path, *args, **kwargs)


class TestRunGitTimed:
    """Unit tests for run_git_timed with subprocess mocked."""

    def test_success_passes_output_through(self, tmp_path: Path) -> None:
        """Exit 0 gives success with stdout and stderr unchanged."""
        run_mock = MagicMock(return_value=_completed(0, "out\n", "err\n"))

        result = _run_patched(tmp_path, run_mock, "push", "origin")

        assert result == {
            "success": True,
            "error": None,
            "returncode": 0,
            "stderr": "err\n",
            "stdout": "out\n",
        }

    def test_nonzero_exit_is_failure(self, tmp_path: Path) -> None:
        """A non-zero exit names the subcommand and keeps stderr."""
        run_mock = MagicMock(return_value=_completed(1, "", "rejected\n"))

        result = _run_patched(tmp_path, run_mock, "push", "origin")

        assert result["success"] is False
        assert result["error"] == "git push failed (exit 1)"
        assert result["returncode"] == 1
        assert result["stderr"] == "rejected\n"

    def test_timeout_is_failure_without_process(self, tmp_path: Path) -> None:
        """A timeout reports the limit and no returncode."""
        run_mock = MagicMock(
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=120)
        )

        result = _run_patched(tmp_path, run_mock, "push", "origin")

        assert result["success"] is False
        assert result["error"] == "git push timed out after 120 s"
        assert result["returncode"] is None
        assert result["stderr"] is None
        assert result["stdout"] == ""

    def test_os_error_is_failure(self, tmp_path: Path) -> None:
        """An OSError starting git is reported, not raised."""
        run_mock = MagicMock(side_effect=OSError("boom"))

        result = _run_patched(tmp_path, run_mock, "push")

        assert result["success"] is False
        assert result["error"] == "git push could not run: boom"
        assert result["returncode"] is None

    def test_git_not_on_path(self, tmp_path: Path) -> None:
        """No git binary gives a failure without running anything."""
        run_mock = MagicMock()
        with (
            patch(f"{MODULE}.shutil.which", return_value=None),
            patch(f"{MODULE}.subprocess.run", run_mock),
        ):
            result = run_git_timed(tmp_path, "push")

        assert result["success"] is False
        assert result["error"] is not None
        assert "not found" in result["error"]
        assert result["returncode"] is None
        assert result["stdout"] == ""
        run_mock.assert_not_called()

    def test_credentials_scrubbed_from_output(self, tmp_path: Path) -> None:
        """Userinfo in URLs is removed from stdout and stderr."""
        url = "https://user:tok@host/x"
        run_mock = MagicMock(return_value=_completed(1, f"to {url}\n", f"at {url}\n"))

        result = _run_patched(tmp_path, run_mock, "push")

        assert result["stdout"] == "to https://host/x\n"
        assert result["stderr"] == "at https://host/x\n"
        assert "tok" not in (result["error"] or "")

    def test_call_discipline(self, tmp_path: Path) -> None:
        """The call is non-interactive, bounded, and runs in project_dir."""
        run_mock = MagicMock(return_value=_completed(0))

        _run_patched(tmp_path, run_mock, "ls-remote", "origin", timeout=7.5)

        run_mock.assert_called_once()
        argv = run_mock.call_args.args[0]
        kwargs = run_mock.call_args.kwargs
        assert argv == [GIT_PATH, "ls-remote", "origin"]
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["timeout"] == 7.5
        assert kwargs["cwd"] == tmp_path
        assert kwargs["check"] is False

    def test_default_timeout(self, tmp_path: Path) -> None:
        """Without a timeout argument the network default applies."""
        run_mock = MagicMock(return_value=_completed(0))

        _run_patched(tmp_path, run_mock, "push")

        assert run_mock.call_args.kwargs["timeout"] == GIT_NETWORK_TIMEOUT == 120.0

    def test_credential_manager_dialog_disabled(self, tmp_path: Path) -> None:
        """Git Credential Manager may not open a dialog that outlives the timeout."""
        run_mock = MagicMock(return_value=_completed(0))

        _run_patched(tmp_path, run_mock, "push")

        assert run_mock.call_args.kwargs["env"]["GCM_INTERACTIVE"] == "never"


@pytest.mark.git_integration
class TestRunGitTimedIntegration:
    """run_git_timed against a real repository."""

    def test_rev_parse_inside_work_tree(self, git_repo: tuple[Repo, Path]) -> None:
        """A real git call succeeds and returns its stdout."""
        _, project_dir = git_repo

        result = run_git_timed(project_dir, "rev-parse", "--is-inside-work-tree")

        assert result["success"] is True
        assert result["returncode"] == 0
        assert result["stdout"] == "true\n"
