"""Tests for git_operations.verification module.

Foundation and Tier 1 baseline tests (git_binary, git_repo, user_identity,
overall_ok). The signing-detection Tier 1 tests live in
``test_verification_tier1_signing.py`` to keep this file under the line
budget.
"""

import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest
from git.exc import GitCommandError

from mcp_workspace.git_operations.verification import (
    CheckResult,
    _get_config,
    _run,
    verify_git,
)

MODULE = "mcp_workspace.git_operations.verification"


def _patch_baseline_ok(
    project_dir: Path,
    *,
    git_path: Optional[str] = "/usr/bin/git",
    git_version_stdout: str = "git version 2.42.0",
    git_version_returncode: int = 0,
    is_git_repo: bool = True,
    user_name: Optional[str] = "Alice",
    user_email: Optional[str] = "alice@example.com",
    commit_gpgsign: Optional[str] = None,
    tag_gpgsign: Optional[str] = None,
    rebase_gpgsign: Optional[str] = None,
    push_gpgsign: Optional[str] = None,
    gpg_format: Optional[str] = None,
    user_signingkey: Optional[str] = None,
) -> dict[str, object]:
    """Run verify_git with all Tier 1 dependencies mocked."""

    def fake_run(args: list[str], timeout: float) -> "subprocess.CompletedProcess[str]":
        del timeout
        return subprocess.CompletedProcess(
            args=args,
            returncode=git_version_returncode,
            stdout=git_version_stdout,
            stderr="",
        )

    fake_repo = Mock()

    signing_flags: dict[str, Optional[str]] = {
        "commit.gpgsign": commit_gpgsign,
        "tag.gpgsign": tag_gpgsign,
        "rebase.gpgSign": rebase_gpgsign,
        "push.gpgSign": push_gpgsign,
    }

    def fake_get_config(repo: object, key: str, *extra_args: str) -> Optional[str]:
        del repo, extra_args
        if key == "user.name":
            return user_name
        if key == "user.email":
            return user_email
        if key == "gpg.format":
            return gpg_format
        if key == "user.signingkey":
            return user_signingkey
        if key in signing_flags:
            return signing_flags[key]
        return None

    @contextmanager
    def fake_safe_repo_context(_path: Path) -> Iterator[Mock]:
        yield fake_repo

    with (
        patch(f"{MODULE}.shutil.which", return_value=git_path),
        patch(f"{MODULE}._run", side_effect=fake_run),
        patch(f"{MODULE}.is_git_repository", return_value=is_git_repo),
        patch(f"{MODULE}.safe_repo_context", fake_safe_repo_context),
        patch(f"{MODULE}._get_config", side_effect=fake_get_config),
    ):
        return verify_git(project_dir)


class TestVerifyGit:
    """Tests for the public verify_git function."""

    def test_verify_git_returns_dict_with_overall_ok(self, tmp_path: Path) -> None:
        """verify_git returns a dict containing overall_ok=True."""
        result = _patch_baseline_ok(tmp_path)
        assert isinstance(result, dict)
        assert result["overall_ok"] is True

    def test_verify_git_keyword_only_actually_sign(self, tmp_path: Path) -> None:
        """actually_sign must be passed as a keyword argument."""
        # Cast to Any so mypy does not flag the deliberate misuse: this test
        # asserts the keyword-only contract raises TypeError at runtime.
        verify_git_dyn: Any = verify_git
        with pytest.raises(TypeError):
            # pylint: disable=too-many-function-args
            verify_git_dyn(tmp_path, True)


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

    def test_get_config_does_not_log_value(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The returned value is never logged at debug level (Decision #11)."""
        repo = MagicMock()
        secret = "SECRET-KEY-VALUE-XYZ"
        repo.git.config.return_value = secret
        with caplog.at_level("DEBUG", logger=MODULE):
            _get_config(repo, "user.signingkey")
        assert secret not in caplog.text


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


class TestGitBinary:
    """Tests for the git_binary check."""

    def test_git_binary_ok(self, tmp_path: Path) -> None:
        """git on PATH and runnable → ok=True with version in value."""
        result = _patch_baseline_ok(tmp_path)
        check: CheckResult = result["git_binary"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["severity"] == "error"
        assert "git version" in check["value"]

    def test_git_binary_not_on_path(self, tmp_path: Path) -> None:
        """shutil.which returns None → ok=False, value='not found'."""
        result = _patch_baseline_ok(tmp_path, git_path=None)
        check: CheckResult = result["git_binary"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "not found"
        assert check["severity"] == "error"
        assert "install_hint" in check

    def test_git_binary_runnable_failure(self, tmp_path: Path) -> None:
        """shutil.which succeeds but `git --version` exits non-zero."""
        result = _patch_baseline_ok(
            tmp_path,
            git_version_returncode=1,
            git_version_stdout="",
        )
        check: CheckResult = result["git_binary"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "found but not runnable"
        assert check["severity"] == "error"
        assert "error" in check


class TestGitRepo:
    """Tests for the git_repo check."""

    def test_git_repo_ok(self, tmp_path: Path) -> None:
        """is_git_repository True → ok=True."""
        result = _patch_baseline_ok(tmp_path)
        check: CheckResult = result["git_repo"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["severity"] == "error"
        assert str(tmp_path) in check["value"]

    def test_git_repo_missing(self, tmp_path: Path) -> None:
        """is_git_repository False → ok=False, severity=error."""
        result = _patch_baseline_ok(tmp_path, is_git_repo=False)
        check: CheckResult = result["git_repo"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "not a git repo"
        assert check["severity"] == "error"
        assert "error" in check


class TestUserIdentity:
    """Tests for the user_identity check."""

    def test_user_identity_ok(self, tmp_path: Path) -> None:
        """Both name and email set → ok=True, value contains email."""
        result = _patch_baseline_ok(tmp_path)
        check: CheckResult = result["user_identity"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["severity"] == "error"
        assert "alice@example.com" in check["value"]
        assert "Alice" in check["value"]

    def test_user_identity_missing_name(self, tmp_path: Path) -> None:
        """user.name unset → ok=False, value mentions user.name."""
        result = _patch_baseline_ok(tmp_path, user_name=None)
        check: CheckResult = result["user_identity"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert "user.name" in check["value"]
        assert check["severity"] == "error"
        assert "install_hint" in check

    def test_user_identity_missing_email(self, tmp_path: Path) -> None:
        """user.email unset → ok=False, value mentions user.email."""
        result = _patch_baseline_ok(tmp_path, user_email=None)
        check: CheckResult = result["user_identity"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert "user.email" in check["value"]
        assert check["severity"] == "error"

    def test_user_identity_skipped_when_no_repo(self, tmp_path: Path) -> None:
        """git_repo failed → user_identity reports 'repository not accessible'."""
        result = _patch_baseline_ok(tmp_path, is_git_repo=False)
        check: CheckResult = result["user_identity"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "unknown"
        assert check["severity"] == "error"
        assert check.get("error") == "repository not accessible"


class TestOverallOk:
    """Tests for overall_ok computation across error-severity checks."""

    def test_overall_ok_true_when_all_pass(self, tmp_path: Path) -> None:
        """All three checks pass → overall_ok=True."""
        result = _patch_baseline_ok(tmp_path)
        assert result["overall_ok"] is True

    def test_overall_ok_false_when_git_binary_fails(self, tmp_path: Path) -> None:
        """git_binary failure flips overall_ok to False."""
        result = _patch_baseline_ok(tmp_path, git_path=None)
        assert result["overall_ok"] is False

    def test_overall_ok_false_when_git_repo_fails(self, tmp_path: Path) -> None:
        """git_repo failure flips overall_ok to False."""
        result = _patch_baseline_ok(tmp_path, is_git_repo=False)
        assert result["overall_ok"] is False

    def test_overall_ok_false_when_user_identity_fails(self, tmp_path: Path) -> None:
        """user_identity failure flips overall_ok to False."""
        result = _patch_baseline_ok(tmp_path, user_name=None, user_email=None)
        assert result["overall_ok"] is False
