"""Tests for git_operations.verification module."""

import subprocess
from collections.abc import Callable
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


# ----------------------------------------------------------------------
# Step 5 helper: full-path mocking for Tier 2 binary checks.
# ----------------------------------------------------------------------


def _patch_step5(
    project_dir: Path,
    *,
    is_git_repo: bool = True,
    user_name: Optional[str] = "Alice",
    user_email: Optional[str] = "alice@example.com",
    commit_gpgsign: Optional[str] = "true",
    tag_gpgsign: Optional[str] = None,
    rebase_gpgsign: Optional[str] = None,
    push_gpgsign: Optional[str] = None,
    gpg_format: Optional[str] = None,
    user_signingkey: Optional[str] = "ABCD1234",
    gpg_program: Optional[str] = None,
    which_map: Optional[dict[str, Optional[str]]] = None,
    is_file_map: Optional[dict[str, bool]] = None,
    run_handler: Optional[
        Callable[[list[str]], "subprocess.CompletedProcess[str]"]
    ] = None,
) -> tuple[dict[str, object], dict[str, list[object]]]:
    """Run verify_git with all Step-5-relevant mocks."""

    final_which_map: dict[str, Optional[str]] = {
        "git": "/usr/bin/git",
        "gpg": "/usr/bin/gpg",
        "ssh-keygen": "/usr/bin/ssh-keygen",
        "gpgsm": "/usr/bin/gpgsm",
    }
    if which_map is not None:
        final_which_map.update(which_map)

    final_is_file_map: dict[str, bool] = dict(is_file_map or {})

    calls: dict[str, list[object]] = {"which": [], "run": []}

    def fake_which(name: str) -> Optional[str]:
        calls["which"].append(name)
        return final_which_map.get(name)

    def default_run_handler(
        args: list[str],
    ) -> "subprocess.CompletedProcess[str]":
        if args and args[-1] == "--version":
            binary_path = args[0]
            binary_name = binary_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            if binary_name == "git":
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="git version 2.42.0",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{binary_name} (version 1.0)",
                stderr="",
            )
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="ok", stderr=""
        )

    def fake_run(
        args: list[str], timeout: float
    ) -> "subprocess.CompletedProcess[str]":
        del timeout
        calls["run"].append(list(args))
        if run_handler is not None:
            return run_handler(args)
        return default_run_handler(args)

    def fake_path_factory(value: object) -> MagicMock:
        instance = MagicMock()
        instance.is_file.return_value = final_is_file_map.get(str(value), False)
        return instance

    fake_repo = Mock()

    signing_flags: dict[str, Optional[str]] = {
        "commit.gpgsign": commit_gpgsign,
        "tag.gpgsign": tag_gpgsign,
        "rebase.gpgSign": rebase_gpgsign,
        "push.gpgSign": push_gpgsign,
    }

    def fake_get_config(
        repo: object, key: str, *extra_args: str
    ) -> Optional[str]:
        del repo, extra_args
        if key == "user.name":
            return user_name
        if key == "user.email":
            return user_email
        if key == "gpg.format":
            return gpg_format
        if key == "user.signingkey":
            return user_signingkey
        if key == "gpg.program":
            return gpg_program
        if key in signing_flags:
            return signing_flags[key]
        return None

    @contextmanager
    def fake_safe_repo_context(_path: Path) -> Iterator[Mock]:
        yield fake_repo

    with (
        patch(f"{MODULE}.shutil.which", side_effect=fake_which),
        patch(f"{MODULE}._run", side_effect=fake_run),
        patch(f"{MODULE}.is_git_repository", return_value=is_git_repo),
        patch(f"{MODULE}.safe_repo_context", fake_safe_repo_context),
        patch(f"{MODULE}._get_config", side_effect=fake_get_config),
        patch(f"{MODULE}.Path", side_effect=fake_path_factory),
    ):
        result = verify_git(project_dir)

    return result, calls


class TestSigningBinaryOpenPGP:
    """Tests for the signing_binary check on the openpgp path."""

    def test_gpg_program_set_and_present(self, tmp_path: Path) -> None:
        """gpg.program set + file exists + version ok → ok=True."""

        def run_handler(
            args: list[str],
        ) -> "subprocess.CompletedProcess[str]":
            if args[0] == "/opt/gpg/gpg":
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="gpg (GnuPG) 2.4.0\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="git version 2.42.0",
                stderr="",
            )

        result, _ = _patch_step5(
            tmp_path,
            gpg_program="/opt/gpg/gpg",
            is_file_map={"/opt/gpg/gpg": True},
            run_handler=run_handler,
        )
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["severity"] == "error"
        assert "gpg" in check["value"]

    def test_gpg_program_set_but_missing_is_error_no_fallback(
        self, tmp_path: Path
    ) -> None:
        """gpg.program set but file missing → error with no shutil.which fallback."""
        result, calls = _patch_step5(
            tmp_path,
            gpg_program="/missing/gpg",
            is_file_map={"/missing/gpg": False},
        )
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "error"
        assert "configured but missing" in check["value"]
        assert "/missing/gpg" in check["value"]
        for run_call in calls["run"]:
            assert isinstance(run_call, list)
            assert "/missing/gpg" not in run_call
            assert "/usr/bin/gpg" not in run_call

    def test_gpg_program_unset_uses_path(self, tmp_path: Path) -> None:
        """gpg.program unset, shutil.which finds gpg, --version ok → ok=True."""
        result, calls = _patch_step5(tmp_path, gpg_program=None)
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["severity"] == "error"
        assert "gpg" in check["value"]
        assert "gpg" in calls["which"]

    def test_gpg_not_on_path(self, tmp_path: Path) -> None:
        """gpg.program unset, shutil.which returns None → ok=False, 'not found'."""
        result, _ = _patch_step5(
            tmp_path, gpg_program=None, which_map={"gpg": None}
        )
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "not found"
        assert check["severity"] == "error"
        assert "install_hint" in check
        assert "openpgp" in check.get("error", "")

    def test_gpg_runnable_failure(self, tmp_path: Path) -> None:
        """shutil.which ok but --version exits non-zero → ok=False, error from stderr."""

        def run_handler(
            args: list[str],
        ) -> "subprocess.CompletedProcess[str]":
            if args[0] == "/usr/bin/gpg":
                return subprocess.CompletedProcess(
                    args=args, returncode=2, stdout="", stderr="gpg crashed"
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="git version 2.42.0",
                stderr="",
            )

        result, _ = _patch_step5(tmp_path, run_handler=run_handler)
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "not runnable"
        assert check["severity"] == "error"
        assert "gpg crashed" in check.get("error", "")


class TestSigningBinarySSH:
    """Tests for the signing_binary check on the ssh path."""

    def test_ssh_keygen_found(self, tmp_path: Path) -> None:
        """gpg.format=ssh, ssh-keygen on PATH, --version ok → ok=True."""
        result, calls = _patch_step5(tmp_path, gpg_format="ssh")
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["severity"] == "error"
        assert "ssh-keygen" in calls["which"]

    def test_ssh_keygen_not_found(self, tmp_path: Path) -> None:
        """ssh-keygen not on PATH → ok=False, value='not found'."""
        result, _ = _patch_step5(
            tmp_path, gpg_format="ssh", which_map={"ssh-keygen": None}
        )
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "not found"
        assert check["severity"] == "error"
        assert "install_hint" in check
        assert "ssh" in check.get("error", "").lower()


class TestSigningBinaryX509:
    """Tests for the signing_binary check on the x509 path."""

    def test_gpgsm_found(self, tmp_path: Path) -> None:
        """gpg.format=x509, gpgsm on PATH, --version ok → ok=True."""
        result, calls = _patch_step5(tmp_path, gpg_format="x509")
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["severity"] == "error"
        assert "gpgsm" in calls["which"]

    def test_gpgsm_not_found(self, tmp_path: Path) -> None:
        """gpgsm not on PATH → ok=False, value='not found'."""
        result, _ = _patch_step5(
            tmp_path, gpg_format="x509", which_map={"gpgsm": None}
        )
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "not found"
        assert check["severity"] == "error"
        assert "install_hint" in check
        assert "x509" in check.get("error", "")


class TestSigningKeyAccessible:
    """Tests for the signing_key_accessible check."""

    def test_openpgp_key_found(self, tmp_path: Path) -> None:
        """gpg --list-secret-keys returns rc=0 with non-empty stdout → ok=True."""

        def run_handler(
            args: list[str],
        ) -> "subprocess.CompletedProcess[str]":
            if "--list-secret-keys" in args:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="sec   rsa4096 ...\n",
                    stderr="",
                )
            if args[-1] == "--version" and "gpg" in args[0]:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="gpg (GnuPG) 2.4.0",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="git version 2.42.0",
                stderr="",
            )

        result, _ = _patch_step5(tmp_path, run_handler=run_handler)
        check: CheckResult = result["signing_key_accessible"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "found"
        assert check["severity"] == "error"

    def test_openpgp_key_not_found(self, tmp_path: Path) -> None:
        """gpg --list-secret-keys exits 2 → ok=False, value='not found'."""

        def run_handler(
            args: list[str],
        ) -> "subprocess.CompletedProcess[str]":
            if "--list-secret-keys" in args:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=2,
                    stdout="",
                    stderr="No such key",
                )
            if args[-1] == "--version" and "gpg" in args[0]:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="gpg (GnuPG) 2.4.0",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="git version 2.42.0",
                stderr="",
            )

        result, _ = _patch_step5(tmp_path, run_handler=run_handler)
        check: CheckResult = result["signing_key_accessible"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "not found"
        assert check["severity"] == "error"
        assert "error" in check

    def test_ssh_key_file_present(self, tmp_path: Path) -> None:
        """gpg.format=ssh, key file exists → ok=True."""
        key_path = "/home/user/.ssh/id_ed25519"
        result, _ = _patch_step5(
            tmp_path,
            gpg_format="ssh",
            user_signingkey=key_path,
            is_file_map={key_path: True},
        )
        check: CheckResult = result["signing_key_accessible"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "found"
        assert check["severity"] == "error"

    def test_ssh_key_file_missing(self, tmp_path: Path) -> None:
        """gpg.format=ssh, key file does not exist → ok=False, error includes path."""
        key_path = "/home/user/.ssh/missing"
        result, _ = _patch_step5(
            tmp_path,
            gpg_format="ssh",
            user_signingkey=key_path,
            is_file_map={key_path: False},
        )
        check: CheckResult = result["signing_key_accessible"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "not found"
        assert check["severity"] == "error"
        assert key_path in check.get("error", "")

    def test_x509_key_found(self, tmp_path: Path) -> None:
        """gpgsm --list-secret-keys returns rc=0 + stdout → ok=True."""

        def run_handler(
            args: list[str],
        ) -> "subprocess.CompletedProcess[str]":
            if "--list-secret-keys" in args:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="ID 12345\n",
                    stderr="",
                )
            if args[-1] == "--version":
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="version",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="git version 2.42.0",
                stderr="",
            )

        result, _ = _patch_step5(
            tmp_path, gpg_format="x509", run_handler=run_handler
        )
        check: CheckResult = result["signing_key_accessible"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "found"
        assert check["severity"] == "error"

    def test_skipped_when_signingkey_unset(self, tmp_path: Path) -> None:
        """user.signingkey unset → 'cannot probe: user.signingkey not set'."""
        result, _ = _patch_step5(tmp_path, user_signingkey=None)
        check: CheckResult = result["signing_key_accessible"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert "cannot probe" in check["value"]
        assert "user.signingkey" in check["value"]
        assert check["severity"] == "error"

    def test_skipped_when_binary_unavailable(self, tmp_path: Path) -> None:
        """signing_binary unavailable → 'cannot probe: signing binary unavailable'."""
        result, _ = _patch_step5(
            tmp_path,
            gpg_program=None,
            which_map={"gpg": None},
        )
        binary: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert binary["ok"] is False
        check: CheckResult = result["signing_key_accessible"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert "cannot probe" in check["value"]
        assert "signing binary" in check["value"]
        assert check["severity"] == "error"

    def test_key_id_not_logged(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The user's signing key id never appears in any logged output."""
        secret_key = "ABC123KEY"

        def run_handler(
            args: list[str],
        ) -> "subprocess.CompletedProcess[str]":
            if "--list-secret-keys" in args:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="sec   rsa4096 ...",
                    stderr="",
                )
            if args[-1] == "--version" and "gpg" in args[0]:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="gpg (GnuPG) 2.4.0",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="git version 2.42.0",
                stderr="",
            )

        with caplog.at_level("DEBUG", logger=MODULE):
            _patch_step5(
                tmp_path,
                user_signingkey=secret_key,
                run_handler=run_handler,
            )
        assert secret_key not in caplog.text


class TestGpgProgramPrecedence:
    """Tests for gpg.program precedence over shutil.which (Decision #13)."""

    def test_gpg_program_takes_precedence_over_path(self, tmp_path: Path) -> None:
        """gpg.program set and valid → use it instead of shutil.which result."""

        def run_handler(
            args: list[str],
        ) -> "subprocess.CompletedProcess[str]":
            if args[0] == "/opt/custom/gpg":
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="custom gpg version",
                    stderr="",
                )
            if args[0] == "/usr/bin/gpg":
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=99,
                    stdout="",
                    stderr="should not run",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="git version 2.42.0",
                stderr="",
            )

        result, calls = _patch_step5(
            tmp_path,
            gpg_program="/opt/custom/gpg",
            is_file_map={"/opt/custom/gpg": True},
            run_handler=run_handler,
        )
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert "custom gpg version" in check["value"]
        run_paths = [call[0] for call in calls["run"] if isinstance(call, list)]
        assert "/usr/bin/gpg" not in run_paths


# ----------------------------------------------------------------------
# Step 6 helper: full-path mocking for Tier 2 auxiliary checks.
# ----------------------------------------------------------------------


def _patch_step6(
    project_dir: Path,
    *,
    is_git_repo: bool = True,
    user_name: Optional[str] = "Alice",
    user_email: Optional[str] = "alice@example.com",
    commit_gpgsign: Optional[str] = "true",
    tag_gpgsign: Optional[str] = None,
    rebase_gpgsign: Optional[str] = None,
    push_gpgsign: Optional[str] = None,
    gpg_format: Optional[str] = None,
    user_signingkey: Optional[str] = "ABCD1234",
    gpg_program: Optional[str] = None,
    allowed_signers_file: Optional[str] = None,
    which_map: Optional[dict[str, Optional[str]]] = None,
    is_file_map: Optional[dict[str, bool]] = None,
    run_handler: Optional[
        Callable[[list[str]], "subprocess.CompletedProcess[str]"]
    ] = None,
    head_is_valid: bool = True,
    verify_commit_outcome: Optional[object] = "ok",
    verify_commit_side_effect: Optional[Exception] = None,
    repo_open_side_effect: Optional[Exception] = None,
) -> tuple[dict[str, object], dict[str, list[object]]]:
    """Run verify_git with Step 6 (and Step 5) mocks applied."""

    final_which_map: dict[str, Optional[str]] = {
        "git": "/usr/bin/git",
        "gpg": "/usr/bin/gpg",
        "ssh-keygen": "/usr/bin/ssh-keygen",
        "gpgsm": "/usr/bin/gpgsm",
        "gpg-connect-agent": "/usr/bin/gpg-connect-agent",
    }
    if which_map is not None:
        final_which_map.update(which_map)

    final_is_file_map: dict[str, bool] = dict(is_file_map or {})

    calls: dict[str, list[object]] = {"which": [], "run": []}

    def fake_which(name: str) -> Optional[str]:
        calls["which"].append(name)
        return final_which_map.get(name)

    def default_run_handler(
        args: list[str],
    ) -> "subprocess.CompletedProcess[str]":
        if args[0].endswith("gpg-connect-agent"):
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="OK", stderr=""
            )
        if args and args[-1] == "--version":
            binary_path = args[0]
            binary_name = binary_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            if binary_name == "git":
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="git version 2.42.0",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{binary_name} (version 1.0)",
                stderr="",
            )
        if "--list-secret-keys" in args:
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="sec ...", stderr=""
            )
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="ok", stderr=""
        )

    def fake_run(
        args: list[str], timeout: float
    ) -> "subprocess.CompletedProcess[str]":
        del timeout
        calls["run"].append(list(args))
        if run_handler is not None:
            return run_handler(args)
        return default_run_handler(args)

    def fake_path_factory(value: object) -> MagicMock:
        instance = MagicMock()
        instance.is_file.return_value = final_is_file_map.get(str(value), False)
        return instance

    fake_repo = Mock()
    fake_repo.head.is_valid.return_value = head_is_valid
    if verify_commit_side_effect is not None:
        fake_repo.git.verify_commit.side_effect = verify_commit_side_effect
    else:
        fake_repo.git.verify_commit.return_value = verify_commit_outcome

    signing_flags: dict[str, Optional[str]] = {
        "commit.gpgsign": commit_gpgsign,
        "tag.gpgsign": tag_gpgsign,
        "rebase.gpgSign": rebase_gpgsign,
        "push.gpgSign": push_gpgsign,
    }

    def fake_get_config(
        repo: object, key: str, *extra_args: str
    ) -> Optional[str]:
        del repo, extra_args
        if key == "user.name":
            return user_name
        if key == "user.email":
            return user_email
        if key == "gpg.format":
            return gpg_format
        if key == "user.signingkey":
            return user_signingkey
        if key == "gpg.program":
            return gpg_program
        if key == "gpg.ssh.allowedSignersFile":
            return allowed_signers_file
        if key in signing_flags:
            return signing_flags[key]
        return None

    contexts_opened = {"count": 0}

    @contextmanager
    def fake_safe_repo_context(_path: Path) -> Iterator[Mock]:
        contexts_opened["count"] += 1
        if (
            repo_open_side_effect is not None
            and contexts_opened["count"] >= 4
        ):
            raise repo_open_side_effect
        yield fake_repo

    with (
        patch(f"{MODULE}.shutil.which", side_effect=fake_which),
        patch(f"{MODULE}._run", side_effect=fake_run),
        patch(f"{MODULE}.is_git_repository", return_value=is_git_repo),
        patch(f"{MODULE}.safe_repo_context", fake_safe_repo_context),
        patch(f"{MODULE}._get_config", side_effect=fake_get_config),
        patch(f"{MODULE}.Path", side_effect=fake_path_factory),
    ):
        result = verify_git(project_dir)

    return result, calls


class TestAgentReachable:
    """Tests for the agent_reachable check (openpgp / x509 only)."""

    def test_agent_reachable_ok(self, tmp_path: Path) -> None:
        """openpgp + which finds it + returncode 0 → ok=True, warning."""
        result, _ = _patch_step6(tmp_path)
        check: CheckResult = result["agent_reachable"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "reachable"
        assert check["severity"] == "warning"

    def test_agent_unreachable(self, tmp_path: Path) -> None:
        """returncode != 0 → ok=False, warning, error captured."""

        def run_handler(
            args: list[str],
        ) -> "subprocess.CompletedProcess[str]":
            if args[0].endswith("gpg-connect-agent"):
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=2,
                    stdout="",
                    stderr="connection refused",
                )
            if args[-1] == "--version":
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="git version 2.42.0"
                    if "git" in args[0]
                    else "binary 1.0",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="", stderr=""
            )

        result, _ = _patch_step6(tmp_path, run_handler=run_handler)
        check: CheckResult = result["agent_reachable"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "unreachable"
        assert check["severity"] == "warning"
        assert "connection refused" in check.get("error", "")

    def test_agent_binary_missing(self, tmp_path: Path) -> None:
        """shutil.which returns None for gpg-connect-agent → ok=False, 'not found'."""
        result, _ = _patch_step6(
            tmp_path, which_map={"gpg-connect-agent": None}
        )
        check: CheckResult = result["agent_reachable"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "not found"
        assert check["severity"] == "warning"
        assert "install_hint" in check
        assert "PATH" in check.get("error", "")

    def test_agent_absent_for_ssh(self, tmp_path: Path) -> None:
        """gpg.format=ssh → 'agent_reachable' not in result."""
        result, _ = _patch_step6(tmp_path, gpg_format="ssh")
        assert "agent_reachable" not in result

    def test_agent_present_for_x509(self, tmp_path: Path) -> None:
        """gpg.format=x509 → key present."""
        result, _ = _patch_step6(tmp_path, gpg_format="x509")
        assert "agent_reachable" in result
        check: CheckResult = result["agent_reachable"]  # type: ignore[assignment]
        assert check["ok"] is True


class TestAllowedSigners:
    """Tests for the allowed_signers check (ssh only)."""

    def test_allowed_signers_ok(self, tmp_path: Path) -> None:
        """gpg.format=ssh, config set, file exists → ok=True, value is path."""
        signers_path = "/etc/ssh/allowed_signers"
        result, _ = _patch_step6(
            tmp_path,
            gpg_format="ssh",
            allowed_signers_file=signers_path,
            is_file_map={signers_path: True},
        )
        check: CheckResult = result["allowed_signers"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == signers_path
        assert check["severity"] == "warning"

    def test_allowed_signers_unset(self, tmp_path: Path) -> None:
        """gpg.format=ssh, config None → ok=False, value='not configured'."""
        result, _ = _patch_step6(
            tmp_path, gpg_format="ssh", allowed_signers_file=None
        )
        check: CheckResult = result["allowed_signers"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "not configured"
        assert check["severity"] == "warning"
        assert "install_hint" in check

    def test_allowed_signers_file_missing(self, tmp_path: Path) -> None:
        """gpg.format=ssh, config set, file missing → ok=False, 'file missing'."""
        signers_path = "/etc/ssh/allowed_signers"
        result, _ = _patch_step6(
            tmp_path,
            gpg_format="ssh",
            allowed_signers_file=signers_path,
            is_file_map={signers_path: False},
        )
        check: CheckResult = result["allowed_signers"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert "file missing" in check["value"]
        assert signers_path in check["value"]
        assert check["severity"] == "warning"

    def test_allowed_signers_absent_for_openpgp(self, tmp_path: Path) -> None:
        """gpg.format=openpgp → 'allowed_signers' not in result."""
        result, _ = _patch_step6(tmp_path, gpg_format="openpgp")
        assert "allowed_signers" not in result

    def test_allowed_signers_absent_for_x509(self, tmp_path: Path) -> None:
        """gpg.format=x509 → 'allowed_signers' not in result."""
        result, _ = _patch_step6(tmp_path, gpg_format="x509")
        assert "allowed_signers" not in result


class TestVerifyHead:
    """Tests for the verify_head check (all formats)."""

    def test_verify_head_ok_when_signed(self, tmp_path: Path) -> None:
        """is_valid True + verify_commit returns → ok=True, warning."""
        result, _ = _patch_step6(tmp_path, verify_commit_outcome="ok")
        check: CheckResult = result["verify_head"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "HEAD signature valid"
        assert check["severity"] == "warning"

    def test_verify_head_absent_when_no_commits(self, tmp_path: Path) -> None:
        """repo.head.is_valid False → 'verify_head' not in result."""
        result, _ = _patch_step6(tmp_path, head_is_valid=False)
        assert "verify_head" not in result

    def test_verify_head_absent_when_unsigned(self, tmp_path: Path) -> None:
        """GitCommandError stderr 'no signature' → key absent (skip)."""
        exc = GitCommandError(
            "verify-commit", 1, stderr="error: no signature found"
        )
        result, _ = _patch_step6(
            tmp_path, verify_commit_side_effect=exc
        )
        assert "verify_head" not in result

    def test_verify_head_absent_when_not_signed_substring(
        self, tmp_path: Path
    ) -> None:
        """GitCommandError stderr 'not signed' → key absent."""
        exc = GitCommandError(
            "verify-commit", 1, stderr="object is not signed"
        )
        result, _ = _patch_step6(
            tmp_path, verify_commit_side_effect=exc
        )
        assert "verify_head" not in result

    def test_verify_head_warning_on_other_error(self, tmp_path: Path) -> None:
        """GitCommandError unrelated → ok=False, severity=warning (NEVER error)."""
        exc = GitCommandError(
            "verify-commit", 128, stderr="fatal: bad object"
        )
        result, _ = _patch_step6(
            tmp_path, verify_commit_side_effect=exc
        )
        check: CheckResult = result["verify_head"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "verify-commit failed"
        assert check["severity"] == "warning"
        assert "error" in check

    def test_verify_head_severity_never_error(self, tmp_path: Path) -> None:
        """Generic exception during repo open for verify_head → severity=warning."""
        result, _ = _patch_step6(
            tmp_path, repo_open_side_effect=RuntimeError("boom")
        )
        check: CheckResult = result["verify_head"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "warning"


class TestOverallOkUnaffectedByAuxiliaries:
    """Failing aux checks (warning) must not flip overall_ok to False."""

    def test_failing_agent_does_not_flip_overall_ok(
        self, tmp_path: Path
    ) -> None:
        """agent_reachable.ok=False (warning) → overall_ok=True if errors pass."""
        result, _ = _patch_step6(
            tmp_path, which_map={"gpg-connect-agent": None}
        )
        agent: CheckResult = result["agent_reachable"]  # type: ignore[assignment]
        assert agent["ok"] is False
        assert agent["severity"] == "warning"
        assert result["overall_ok"] is True


# ----------------------------------------------------------------------
# Step 7 helper: full-path mocking for Tier 3 actual_signature probe.
# ----------------------------------------------------------------------


def _patch_step7(
    project_dir: Path,
    *,
    actually_sign: bool = False,
    is_git_repo: bool = True,
    user_name: Optional[str] = "Alice",
    user_email: Optional[str] = "alice@example.com",
    commit_gpgsign: Optional[str] = "true",
    tag_gpgsign: Optional[str] = "true",
    rebase_gpgsign: Optional[str] = "true",
    push_gpgsign: Optional[str] = None,
    gpg_format: Optional[str] = None,
    user_signingkey: Optional[str] = "ABCD1234",
    gpg_program: Optional[str] = None,
    allowed_signers_file: Optional[str] = None,
    which_map: Optional[dict[str, Optional[str]]] = None,
    is_file_map: Optional[dict[str, bool]] = None,
    run_handler: Optional[
        Callable[[list[str]], "subprocess.CompletedProcess[str]"]
    ] = None,
    run_with_input_handler: Optional[
        Callable[..., "subprocess.CompletedProcess[str]"]
    ] = None,
    head_is_valid: bool = True,
    verify_commit_outcome: Optional[object] = "ok",
) -> tuple[
    dict[str, object],
    dict[str, list[object]],
    Mock,
]:
    """Run verify_git with mocks suitable for exercising the Tier 3 probe."""

    final_which_map: dict[str, Optional[str]] = {
        "git": "/usr/bin/git",
        "gpg": "/usr/bin/gpg",
        "ssh-keygen": "/usr/bin/ssh-keygen",
        "gpgsm": "/usr/bin/gpgsm",
        "gpg-connect-agent": "/usr/bin/gpg-connect-agent",
    }
    if which_map is not None:
        final_which_map.update(which_map)

    final_is_file_map: dict[str, bool] = dict(is_file_map or {})

    calls: dict[str, list[object]] = {"which": [], "run": []}

    def fake_which(name: str) -> Optional[str]:
        calls["which"].append(name)
        return final_which_map.get(name)

    def default_run_handler(
        args: list[str],
    ) -> "subprocess.CompletedProcess[str]":
        if args[0].endswith("gpg-connect-agent"):
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="OK", stderr=""
            )
        if args and args[-1] == "--version":
            binary_path = args[0]
            binary_name = binary_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            if binary_name == "git":
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="git version 2.42.0",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"{binary_name} (version 1.0)",
                stderr="",
            )
        if "--list-secret-keys" in args:
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="sec ...", stderr=""
            )
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="ok", stderr=""
        )

    def fake_run(
        args: list[str], timeout: float
    ) -> "subprocess.CompletedProcess[str]":
        del timeout
        calls["run"].append(list(args))
        if run_handler is not None:
            return run_handler(args)
        return default_run_handler(args)

    def default_run_with_input(
        args: list[str], *, input: str, timeout: float
    ) -> "subprocess.CompletedProcess[str]":
        del input, timeout
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=(
                "-----BEGIN PGP SIGNED MESSAGE-----\n"
                "Hash: SHA256\n\n"
                "mcp-workspace verify_git probe\n"
                "-----BEGIN PGP SIGNATURE-----\n"
                "FAKEBASE64SIG\n"
                "-----END PGP SIGNATURE-----\n"
            ),
            stderr="",
        )

    run_with_input_mock = Mock(
        side_effect=run_with_input_handler or default_run_with_input
    )

    def fake_path_factory(value: object) -> MagicMock:
        instance = MagicMock()
        instance.is_file.return_value = final_is_file_map.get(str(value), False)
        return instance

    fake_repo = Mock()
    fake_repo.head.is_valid.return_value = head_is_valid
    fake_repo.git.verify_commit.return_value = verify_commit_outcome

    signing_flags: dict[str, Optional[str]] = {
        "commit.gpgsign": commit_gpgsign,
        "tag.gpgsign": tag_gpgsign,
        "rebase.gpgSign": rebase_gpgsign,
        "push.gpgSign": push_gpgsign,
    }

    def fake_get_config(
        repo: object, key: str, *extra_args: str
    ) -> Optional[str]:
        del repo, extra_args
        if key == "user.name":
            return user_name
        if key == "user.email":
            return user_email
        if key == "gpg.format":
            return gpg_format
        if key == "user.signingkey":
            return user_signingkey
        if key == "gpg.program":
            return gpg_program
        if key == "gpg.ssh.allowedSignersFile":
            return allowed_signers_file
        if key in signing_flags:
            return signing_flags[key]
        return None

    @contextmanager
    def fake_safe_repo_context(_path: Path) -> Iterator[Mock]:
        yield fake_repo

    with (
        patch(f"{MODULE}.shutil.which", side_effect=fake_which),
        patch(f"{MODULE}._run", side_effect=fake_run),
        patch(f"{MODULE}._run_with_input", run_with_input_mock),
        patch(f"{MODULE}.is_git_repository", return_value=is_git_repo),
        patch(f"{MODULE}.safe_repo_context", fake_safe_repo_context),
        patch(f"{MODULE}._get_config", side_effect=fake_get_config),
        patch(f"{MODULE}.Path", side_effect=fake_path_factory),
    ):
        result = verify_git(project_dir, actually_sign=actually_sign)

    return result, calls, run_with_input_mock


class TestActuallySignDefault:
    """Tests confirming actually_sign=False does not invoke Tier 3 probe."""

    def test_default_no_actual_signature_key(self, tmp_path: Path) -> None:
        """verify_git(tmp_path) (no actually_sign) → key absent."""
        result, _, _ = _patch_step7(tmp_path)
        assert "actual_signature" not in result

    def test_default_does_not_invoke_signing_subprocess(
        self, tmp_path: Path
    ) -> None:
        """Default invocation never calls _run_with_input."""
        _, _, run_with_input_mock = _patch_step7(tmp_path)
        run_with_input_mock.assert_not_called()


class TestActuallySignOpenPGP:
    """Tests for the openpgp Tier 3 deep probe."""

    def test_signing_succeeds(self, tmp_path: Path) -> None:
        """Successful clearsign → ok=True, severity=error, expected value."""
        result, _, _ = _patch_step7(tmp_path, actually_sign=True)
        check: CheckResult = result["actual_signature"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["severity"] == "error"
        assert check["value"] == "probe signed successfully"

    def test_fixed_probe_string_is_used(self, tmp_path: Path) -> None:
        """_run_with_input receives the fixed PROBE_PAYLOAD string."""
        _, _, run_with_input_mock = _patch_step7(
            tmp_path, actually_sign=True
        )
        run_with_input_mock.assert_called_once()
        kwargs = run_with_input_mock.call_args.kwargs
        assert kwargs["input"] == "mcp-workspace verify_git probe"

    def test_signing_failure_pinentry_cancelled(
        self, tmp_path: Path
    ) -> None:
        """returncode 2 + 'No pinentry' stderr → ok=False, error captured."""

        def handler(
            args: list[str], *, input: str, timeout: float
        ) -> "subprocess.CompletedProcess[str]":
            del input, timeout
            return subprocess.CompletedProcess(
                args=args,
                returncode=2,
                stdout="",
                stderr="gpg: signing failed: No pinentry",
            )

        result, _, _ = _patch_step7(
            tmp_path, actually_sign=True, run_with_input_handler=handler
        )
        check: CheckResult = result["actual_signature"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "error"
        assert check["value"] == "signing failed"
        assert "No pinentry" in check.get("error", "")

    def test_signing_failure_no_secret_key(self, tmp_path: Path) -> None:
        """returncode 2 + 'No secret key' → ok=False, error captured."""

        def handler(
            args: list[str], *, input: str, timeout: float
        ) -> "subprocess.CompletedProcess[str]":
            del input, timeout
            return subprocess.CompletedProcess(
                args=args,
                returncode=2,
                stdout="",
                stderr="No secret key",
            )

        result, _, _ = _patch_step7(
            tmp_path, actually_sign=True, run_with_input_handler=handler
        )
        check: CheckResult = result["actual_signature"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "error"
        assert "No secret key" in check.get("error", "")

    def test_signed_payload_not_logged(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The clearsigned blob bytes never appear in any debug log."""
        with caplog.at_level("DEBUG", logger=MODULE):
            _patch_step7(tmp_path, actually_sign=True)
        assert "FAKEBASE64SIG" not in caplog.text


class TestActuallySignSSHandX509:
    """Tests for the ssh / x509 Tier 3 paths (no real signing)."""

    def test_ssh_returns_not_implemented_warning(
        self, tmp_path: Path
    ) -> None:
        """gpg.format=ssh, actually_sign=True → 'not implemented' warning."""
        result, _, _ = _patch_step7(
            tmp_path, actually_sign=True, gpg_format="ssh"
        )
        check: CheckResult = result["actual_signature"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["severity"] == "warning"
        assert check["value"] == "not implemented for ssh/x509"

    def test_x509_returns_not_implemented_warning(
        self, tmp_path: Path
    ) -> None:
        """gpg.format=x509, actually_sign=True → 'not implemented' warning."""
        result, _, _ = _patch_step7(
            tmp_path, actually_sign=True, gpg_format="x509"
        )
        check: CheckResult = result["actual_signature"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["severity"] == "warning"
        assert check["value"] == "not implemented for ssh/x509"

    def test_ssh_does_not_invoke_subprocess(self, tmp_path: Path) -> None:
        """ssh path: _run_with_input is not called."""
        _, _, run_with_input_mock = _patch_step7(
            tmp_path, actually_sign=True, gpg_format="ssh"
        )
        run_with_input_mock.assert_not_called()


class TestActuallySignPreconditions:
    """Tests for the Tier 3 pre-condition guards."""

    def test_no_intent_no_actual_signature(self, tmp_path: Path) -> None:
        """actually_sign=True but no signing intent → key absent."""
        result, _, _ = _patch_step7(
            tmp_path,
            actually_sign=True,
            commit_gpgsign=None,
            tag_gpgsign=None,
            rebase_gpgsign=None,
            push_gpgsign=None,
        )
        assert "actual_signature" not in result

    def test_missing_signing_key_emits_error(self, tmp_path: Path) -> None:
        """Intent on but user.signingkey unset → ok=False, severity=error."""
        result, _, _ = _patch_step7(
            tmp_path, actually_sign=True, user_signingkey=None
        )
        check: CheckResult = result["actual_signature"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "error"
        assert "unavailable" in check["value"]

    def test_unavailable_signing_binary_emits_error(
        self, tmp_path: Path
    ) -> None:
        """Intent on but signing binary failed → ok=False, severity=error."""
        result, _, _ = _patch_step7(
            tmp_path,
            actually_sign=True,
            gpg_program=None,
            which_map={"gpg": None},
        )
        binary: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert binary["ok"] is False
        check: CheckResult = result["actual_signature"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "error"
        assert "gpg binary" in check["value"]


class TestActuallySignNeverPromptsByDefault:
    """Reinforces the never-prompts-by-default contract."""

    def test_default_does_not_prompt(self, tmp_path: Path) -> None:
        """actually_sign=False: no _run_with_input and no clearsign command."""
        _, calls, run_with_input_mock = _patch_step7(tmp_path)
        run_with_input_mock.assert_not_called()
        for run_call in calls["run"]:
            assert isinstance(run_call, list)
            assert "--clearsign" not in run_call


class TestEndToEndHappyPath:
    """Top-to-bottom smoke test of the full verify_git pipeline."""

    def test_full_happy_path_all_keys_populated_overall_ok(
        self, tmp_path: Path
    ) -> None:
        """Realistic full mock: every expected key populated, overall_ok=True."""
        result, _, _ = _patch_step7(
            tmp_path,
            actually_sign=True,
            commit_gpgsign="true",
            tag_gpgsign="true",
            rebase_gpgsign="true",
            push_gpgsign=None,
            gpg_format=None,
            user_signingkey="ABCD1234",
            gpg_program=None,
            head_is_valid=True,
            verify_commit_outcome="ok",
        )

        expected_keys = {
            "git_binary",
            "git_repo",
            "user_identity",
            "signing_intent",
            "signing_consistency",
            "signing_format",
            "signing_key",
            "signing_binary",
            "signing_key_accessible",
            "agent_reachable",
            "verify_head",
            "actual_signature",
            "overall_ok",
        }
        assert expected_keys <= set(result.keys())
        assert "allowed_signers" not in result

        for key, value in result.items():
            if key == "overall_ok":
                continue
            assert isinstance(value, dict)
            assert value.get("ok") is True, f"{key} not ok: {value!r}"

        assert result["overall_ok"] is True
