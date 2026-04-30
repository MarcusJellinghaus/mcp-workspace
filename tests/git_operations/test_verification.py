"""Tests for git_operations.verification module."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git.exc import GitCommandError

from mcp_workspace.git_operations.verification import (
    CheckResult,
    _get_config,
    _run,
    verify_git,
)


class TestVerifyGit:
    """Tests for the public verify_git function."""

    def test_verify_git_returns_dict_with_overall_ok(self, tmp_path: Path) -> None:
        """verify_git returns a dict containing overall_ok=True."""
        result = verify_git(tmp_path)
        assert isinstance(result, dict)
        assert result["overall_ok"] is True

    def test_verify_git_keyword_only_actually_sign(self, tmp_path: Path) -> None:
        """actually_sign must be passed as a keyword argument."""
        with pytest.raises(TypeError):
            # pylint: disable=too-many-function-args
            verify_git(tmp_path, True)


class TestGetConfig:
    """Tests for the _get_config helper."""

    def test_get_config_returns_value_when_set(self) -> None:
        """Returns the stripped config value when the key is set."""
        repo = MagicMock()
        repo.git.config.return_value = "Alice\n"
        assert _get_config(repo, "user.name") == "Alice"
        repo.git.config.assert_called_once_with("--get", "user.name")

    def test_get_config_returns_none_when_unset(self) -> None:
        """Returns None when git exits non-zero (key unset)."""
        repo = MagicMock()
        repo.git.config.side_effect = GitCommandError("config", 1)
        assert _get_config(repo, "user.name") is None

    def test_get_config_passes_extra_args(self) -> None:
        """Forwards extra positional args to repo.git.config."""
        repo = MagicMock()
        repo.git.config.return_value = "true"
        _get_config(repo, "commit.gpgsign", "--type=bool")
        repo.git.config.assert_called_once_with(
            "--get", "commit.gpgsign", "--type=bool"
        )


class TestRun:
    """Tests for the _run helper."""

    def test_run_uses_subprocess_discipline(self) -> None:
        """_run invokes subprocess.run with the documented arguments."""
        with patch(
            "mcp_workspace.git_operations.verification.subprocess.run"
        ) as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["gpg", "--version"], returncode=0, stdout="", stderr=""
            )
            _run(["gpg", "--version"], timeout=5)
            mock_run.assert_called_once_with(
                ["gpg", "--version"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

    def test_run_timeout_propagates(self) -> None:
        """TimeoutExpired raised by subprocess.run is propagated unchanged."""
        with patch(
            "mcp_workspace.git_operations.verification.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["gpg"], timeout=5),
        ):
            with pytest.raises(subprocess.TimeoutExpired):
                _run(["gpg", "--version"], timeout=5)


class TestCheckResult:
    """Smoke tests for the CheckResult TypedDict."""

    def test_check_result_typed_dict_minimal(self) -> None:
        """A minimal CheckResult can be constructed and indexed."""
        cr = CheckResult(ok=True, value="x", severity="error")
        assert cr["ok"] is True
        assert cr["value"] == "x"
        assert cr["severity"] == "error"
