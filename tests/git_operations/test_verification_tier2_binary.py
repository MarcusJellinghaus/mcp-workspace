"""Tests for Tier 2 binary checks in git_operations.verification module."""

import subprocess
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest

from mcp_workspace.git_operations.verification import CheckResult, verify_git

MODULE = "mcp_workspace.git_operations.verification"


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

    def fake_run(args: list[str], timeout: float) -> "subprocess.CompletedProcess[str]":
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
        result, _ = _patch_step5(tmp_path, gpg_program=None, which_map={"gpg": None})
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


class TestSigningBinaryTimeout:
    """Tests that subprocess.TimeoutExpired is wrapped, not propagated."""

    def test_signing_binary_timeout_openpgp(self, tmp_path: Path) -> None:
        """gpg --version times out → ok=False with timeout-specific value."""

        def run_handler(
            args: list[str],
        ) -> "subprocess.CompletedProcess[str]":
            if "gpg" in args[0] and args[-1] == "--version":
                raise subprocess.TimeoutExpired(cmd=args, timeout=5)
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="git version 2.42.0",
                stderr="",
            )

        result, _ = _patch_step5(tmp_path, run_handler=run_handler)
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "error"
        assert "timed out" in check["value"]
        assert "openpgp" in check["value"]
        assert "error" in check
        assert "5s" in check["error"]

    def test_signing_binary_timeout_ssh(self, tmp_path: Path) -> None:
        """ssh-keygen --version times out → ok=False with timeout-specific value."""

        def run_handler(
            args: list[str],
        ) -> "subprocess.CompletedProcess[str]":
            if "ssh-keygen" in args[0] and args[-1] == "--version":
                raise subprocess.TimeoutExpired(cmd=args, timeout=5)
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="git version 2.42.0",
                stderr="",
            )

        result, _ = _patch_step5(tmp_path, gpg_format="ssh", run_handler=run_handler)
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "error"
        assert "timed out" in check["value"]
        assert "ssh" in check["value"]

    def test_signing_binary_timeout_x509(self, tmp_path: Path) -> None:
        """gpgsm --version times out → ok=False with timeout-specific value."""

        def run_handler(
            args: list[str],
        ) -> "subprocess.CompletedProcess[str]":
            if "gpgsm" in args[0] and args[-1] == "--version":
                raise subprocess.TimeoutExpired(cmd=args, timeout=5)
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="git version 2.42.0",
                stderr="",
            )

        result, _ = _patch_step5(tmp_path, gpg_format="x509", run_handler=run_handler)
        check: CheckResult = result["signing_binary"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "error"
        assert "timed out" in check["value"]
        assert "x509" in check["value"]


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
        result, _ = _patch_step5(tmp_path, gpg_format="x509", which_map={"gpgsm": None})
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

        result, _ = _patch_step5(tmp_path, gpg_format="x509", run_handler=run_handler)
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
