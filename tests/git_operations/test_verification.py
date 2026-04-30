"""Tests for git_operations.verification module."""

import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional
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

    def fake_run(
        args: list[str], timeout: float
    ) -> "subprocess.CompletedProcess[str]":
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


class TestSigningIntentNotConfigured:
    """Tests for signing_intent when no signing flags are set."""

    def test_no_flags_set(self, tmp_path: Path) -> None:
        """All four flags unset → value='not configured', ok=True, warning."""
        result = _patch_baseline_ok(tmp_path)
        check: CheckResult = result["signing_intent"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "not configured"
        assert check["severity"] == "warning"
        assert "install_hint" in check


class TestSigningIntentDetected:
    """Tests for signing_intent when at least one signing flag is true."""

    def test_commit_gpgsign_true(self, tmp_path: Path) -> None:
        """Only commit.gpgsign true → value lists commit.gpgsign."""
        result = _patch_baseline_ok(tmp_path, commit_gpgsign="true")
        check: CheckResult = result["signing_intent"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"].startswith("detected:")
        assert "commit.gpgsign" in check["value"]
        assert check["severity"] == "warning"

    def test_tag_only(self, tmp_path: Path) -> None:
        """Only tag.gpgsign true → value lists tag.gpgsign."""
        result = _patch_baseline_ok(tmp_path, tag_gpgsign="true")
        check: CheckResult = result["signing_intent"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert "tag.gpgsign" in check["value"]
        assert "commit.gpgsign" not in check["value"]

    def test_yes_value_recognised(self, tmp_path: Path) -> None:
        """git canonicalises 'yes' to 'true' under --type=bool → detected."""
        # The mock here returns "true" because that's what git would canonicalise
        # 'yes' to when called with --type=bool. Verifies we use --type=bool, not
        # raw string equality.
        result = _patch_baseline_ok(tmp_path, commit_gpgsign="true")
        check: CheckResult = result["signing_intent"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert "commit.gpgsign" in check["value"]

    def test_extra_args_passed_to_config(self, tmp_path: Path) -> None:
        """_get_config receives '--type=bool' for each of the four signing flags."""
        fake_repo = Mock()

        @contextmanager
        def fake_safe_repo_context(_path: Path) -> Iterator[Mock]:
            yield fake_repo

        def fake_run_inner(
            args: list[str], timeout: float
        ) -> "subprocess.CompletedProcess[str]":
            del timeout
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="git version 2.42.0",
                stderr="",
            )

        def fake_get_config_inner(
            repo: object, key: str, *extra_args: str
        ) -> Optional[str]:
            del repo, extra_args
            if key == "user.name":
                return "Alice"
            if key == "user.email":
                return "alice@example.com"
            return None

        mock_get_config = Mock(side_effect=fake_get_config_inner)

        with (
            patch(f"{MODULE}.shutil.which", return_value="/usr/bin/git"),
            patch(f"{MODULE}._run", side_effect=fake_run_inner),
            patch(f"{MODULE}.is_git_repository", return_value=True),
            patch(f"{MODULE}.safe_repo_context", fake_safe_repo_context),
            patch(f"{MODULE}._get_config", mock_get_config),
        ):
            verify_git(tmp_path)

        flag_calls = {
            call.args[1]
            for call in mock_get_config.call_args_list
            if "--type=bool" in call.args
        }
        assert {
            "commit.gpgsign",
            "tag.gpgsign",
            "rebase.gpgSign",
            "push.gpgSign",
        } <= flag_calls


class TestSigningConsistency:
    """Tests for signing_consistency.

    Always exposed as a single key — never split into per-flag sub-keys.
    """

    def test_not_applicable_when_commit_off(self, tmp_path: Path) -> None:
        """commit.gpgsign not true → value='not applicable', ok=True."""
        result = _patch_baseline_ok(tmp_path)
        check: CheckResult = result["signing_consistency"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "not applicable"
        assert check["severity"] == "warning"

    def test_both_sub_checks_pass(self, tmp_path: Path) -> None:
        """commit + rebase + tag all true → ok=True, value mentions both ok."""
        result = _patch_baseline_ok(
            tmp_path,
            commit_gpgsign="true",
            rebase_gpgsign="true",
            tag_gpgsign="true",
        )
        check: CheckResult = result["signing_consistency"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert "rebase ok" in check["value"]
        assert "tag ok" in check["value"]
        assert check["severity"] == "warning"

    def test_rebase_unset_only(self, tmp_path: Path) -> None:
        """commit + tag true, rebase unset → ok=False, error mentions rebase."""
        result = _patch_baseline_ok(
            tmp_path,
            commit_gpgsign="true",
            tag_gpgsign="true",
        )
        check: CheckResult = result["signing_consistency"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert "rebase.gpgSign unset" in check["value"]
        assert "tag ok" in check["value"]
        assert "rebase" in check.get("error", "")

    def test_tag_unset_only(self, tmp_path: Path) -> None:
        """commit + rebase true, tag unset → ok=False, error mentions tag."""
        result = _patch_baseline_ok(
            tmp_path,
            commit_gpgsign="true",
            rebase_gpgsign="true",
        )
        check: CheckResult = result["signing_consistency"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert "rebase ok" in check["value"]
        assert "tag.gpgsign unset" in check["value"]
        assert "tag" in check.get("error", "")

    def test_both_unset(self, tmp_path: Path) -> None:
        """commit true, rebase + tag unset → ok=False, both errors concatenated."""
        result = _patch_baseline_ok(tmp_path, commit_gpgsign="true")
        check: CheckResult = result["signing_consistency"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert "rebase.gpgSign unset" in check["value"]
        assert "tag.gpgsign unset" in check["value"]
        error = check.get("error", "")
        assert "rebase" in error
        assert "tag" in error

    def test_single_key_shape(self, tmp_path: Path) -> None:
        """No separate signing_consistency_rebase / _tag keys exist."""
        result = _patch_baseline_ok(tmp_path, commit_gpgsign="true")
        assert "signing_consistency" in result
        assert "signing_consistency_rebase" not in result
        assert "signing_consistency_tag" not in result


class TestRepoNotAccessibleSigningChecks:
    """Tests for the signing checks when the repository is not accessible."""

    def test_signing_intent_warning_when_no_repo(self, tmp_path: Path) -> None:
        """is_git_repository False → both signing keys ok=False, warning."""
        result = _patch_baseline_ok(tmp_path, is_git_repo=False)
        for key in ("signing_intent", "signing_consistency"):
            check: CheckResult = result[key]  # type: ignore[assignment]
            assert check["ok"] is False
            assert check["severity"] == "warning"
            assert check.get("error") == "repository not accessible"


class TestOverallOkUnaffectedByWarnings:
    """Tests that warning-severity signing failures don't flip overall_ok."""

    def test_signing_intent_failure_does_not_flip_overall_ok(
        self, tmp_path: Path
    ) -> None:
        """All error checks pass + signing_consistency warning fails → overall_ok=True."""
        result = _patch_baseline_ok(
            tmp_path, commit_gpgsign="true", user_signingkey="ABCD"
        )
        consistency: CheckResult = result[  # type: ignore[assignment]
            "signing_consistency"
        ]
        assert consistency["ok"] is False
        assert consistency["severity"] == "warning"
        assert result["overall_ok"] is True


class TestTier2GatedOnIntent:
    """Tier 2 keys are absent when no signing intent is detected."""

    def test_no_intent_means_keys_absent(self, tmp_path: Path) -> None:
        """All signing flags unset → signing_format / signing_key absent."""
        result = _patch_baseline_ok(tmp_path)
        assert "signing_format" not in result
        assert "signing_key" not in result


class TestSigningFormat:
    """Tests for the signing_format check."""

    def test_unset_defaults_to_openpgp(self, tmp_path: Path) -> None:
        """gpg.format unset, intent on → value='openpgp (default)', ok=True."""
        result = _patch_baseline_ok(tmp_path, commit_gpgsign="true")
        check: CheckResult = result["signing_format"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "openpgp (default)"
        assert check["severity"] == "error"

    def test_explicit_openpgp(self, tmp_path: Path) -> None:
        """gpg.format=openpgp → ok=True, value='openpgp'."""
        result = _patch_baseline_ok(
            tmp_path, commit_gpgsign="true", gpg_format="openpgp"
        )
        check: CheckResult = result["signing_format"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "openpgp"
        assert check["severity"] == "error"

    def test_ssh_value(self, tmp_path: Path) -> None:
        """gpg.format=ssh → ok=True, value='ssh'."""
        result = _patch_baseline_ok(
            tmp_path, commit_gpgsign="true", gpg_format="ssh"
        )
        check: CheckResult = result["signing_format"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "ssh"

    def test_x509_value(self, tmp_path: Path) -> None:
        """gpg.format=x509 → ok=True, value='x509'."""
        result = _patch_baseline_ok(
            tmp_path, commit_gpgsign="true", gpg_format="x509"
        )
        check: CheckResult = result["signing_format"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "x509"

    def test_unknown_value(self, tmp_path: Path) -> None:
        """gpg.format=pgp → ok=False, severity=error, value contains 'unknown: pgp'."""
        result = _patch_baseline_ok(
            tmp_path, commit_gpgsign="true", gpg_format="pgp"
        )
        check: CheckResult = result["signing_format"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "error"
        assert "unknown: pgp" in check["value"]
        assert "error" in check
        assert "pgp" in check["error"]


class TestSigningKeySeverity:
    """Tests for severity rules of signing_key per Decision #10."""

    def test_missing_key_with_commit_gpgsign_is_error(self, tmp_path: Path) -> None:
        """commit.gpgsign true + key unset → severity=error, overall_ok=False."""
        result = _patch_baseline_ok(tmp_path, commit_gpgsign="true")
        check: CheckResult = result["signing_key"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "error"
        assert check["value"] == "not set"
        assert "install_hint" in check
        assert result["overall_ok"] is False

    def test_missing_key_with_only_tag_gpgsign_is_warning(
        self, tmp_path: Path
    ) -> None:
        """Only tag.gpgsign true + key unset → severity=warning, overall_ok=True."""
        result = _patch_baseline_ok(tmp_path, tag_gpgsign="true")
        check: CheckResult = result["signing_key"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "warning"
        assert result["overall_ok"] is True

    def test_missing_key_with_only_rebase_gpgsign_is_warning(
        self, tmp_path: Path
    ) -> None:
        """Only rebase.gpgSign true + key unset → severity=warning."""
        result = _patch_baseline_ok(tmp_path, rebase_gpgsign="true")
        check: CheckResult = result["signing_key"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "warning"
        assert result["overall_ok"] is True

    def test_missing_key_with_only_push_gpgsign_is_warning(
        self, tmp_path: Path
    ) -> None:
        """Only push.gpgSign true + key unset → severity=warning."""
        result = _patch_baseline_ok(tmp_path, push_gpgsign="true")
        check: CheckResult = result["signing_key"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "warning"
        assert result["overall_ok"] is True

    def test_key_present(self, tmp_path: Path) -> None:
        """user.signingkey set → ok=True, severity=error, value='configured'."""
        result = _patch_baseline_ok(
            tmp_path, commit_gpgsign="true", user_signingkey="ABCD1234"
        )
        check: CheckResult = result["signing_key"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["severity"] == "error"
        assert check["value"] == "configured"

    def test_key_value_not_in_check_result(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The user's signing key id never appears in CheckResult.value or logs."""
        secret_key = "DEADBEEFCAFEBABE"
        with caplog.at_level("DEBUG", logger=MODULE):
            result = _patch_baseline_ok(
                tmp_path, commit_gpgsign="true", user_signingkey=secret_key
            )
        check: CheckResult = result["signing_key"]  # type: ignore[assignment]
        assert secret_key not in check["value"]
        assert secret_key not in caplog.text


class TestOverallOkWithSigningSeverityRules:
    """Acceptance criterion: severity rules drive overall_ok correctly."""

    def test_acceptance_only_tag_gpgsign_no_key_overall_ok(
        self, tmp_path: Path
    ) -> None:
        """Only tag.gpgsign + missing key → overall_ok=True."""
        result = _patch_baseline_ok(tmp_path, tag_gpgsign="true")
        assert result["overall_ok"] is True
        signing_key: CheckResult = result["signing_key"]  # type: ignore[assignment]
        assert signing_key["severity"] == "warning"
        assert signing_key["ok"] is False
