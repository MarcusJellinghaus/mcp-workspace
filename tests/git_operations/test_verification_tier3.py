"""Tests for the Tier 3 actual_signature deep probe in verification module."""

import subprocess
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest

from mcp_workspace.git_operations.verification import CheckResult, verify_git

MODULE = "mcp_workspace.git_operations.verification"


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

    def fake_run(args: list[str], timeout: float) -> "subprocess.CompletedProcess[str]":
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

    def test_default_does_not_invoke_signing_subprocess(self, tmp_path: Path) -> None:
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
        _, _, run_with_input_mock = _patch_step7(tmp_path, actually_sign=True)
        run_with_input_mock.assert_called_once()
        kwargs = run_with_input_mock.call_args.kwargs
        assert kwargs["input"] == "mcp-workspace verify_git probe"

    def test_signing_failure_pinentry_cancelled(self, tmp_path: Path) -> None:
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

    def test_ssh_returns_not_implemented_warning(self, tmp_path: Path) -> None:
        """gpg.format=ssh, actually_sign=True → 'not implemented' warning."""
        result, _, _ = _patch_step7(tmp_path, actually_sign=True, gpg_format="ssh")
        check: CheckResult = result["actual_signature"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["severity"] == "warning"
        assert check["value"] == "not implemented for ssh/x509"

    def test_x509_returns_not_implemented_warning(self, tmp_path: Path) -> None:
        """gpg.format=x509, actually_sign=True → 'not implemented' warning."""
        result, _, _ = _patch_step7(tmp_path, actually_sign=True, gpg_format="x509")
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
        result, _, _ = _patch_step7(tmp_path, actually_sign=True, user_signingkey=None)
        check: CheckResult = result["actual_signature"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "error"
        assert "unavailable" in check["value"]

    def test_unavailable_signing_binary_emits_error(self, tmp_path: Path) -> None:
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
