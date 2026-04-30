"""Tests for Tier 2 auxiliary checks in git_operations.verification module."""

import subprocess
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional
from unittest.mock import MagicMock, Mock, patch

from git.exc import GitCommandError

from mcp_workspace.git_operations.verification import CheckResult, verify_git

MODULE = "mcp_workspace.git_operations.verification"


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

    contexts_opened = {"count": 0}

    @contextmanager
    def fake_safe_repo_context(_path: Path) -> Iterator[Mock]:
        contexts_opened["count"] += 1
        if repo_open_side_effect is not None and contexts_opened["count"] >= 4:
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
                    stdout="git version 2.42.0" if "git" in args[0] else "binary 1.0",
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
        result, _ = _patch_step6(tmp_path, which_map={"gpg-connect-agent": None})
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
        result, _ = _patch_step6(tmp_path, gpg_format="ssh", allowed_signers_file=None)
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
        exc = GitCommandError("verify-commit", 1, stderr="error: no signature found")
        result, _ = _patch_step6(tmp_path, verify_commit_side_effect=exc)
        assert "verify_head" not in result

    def test_verify_head_absent_when_not_signed_substring(self, tmp_path: Path) -> None:
        """GitCommandError stderr 'not signed' → key absent."""
        exc = GitCommandError("verify-commit", 1, stderr="object is not signed")
        result, _ = _patch_step6(tmp_path, verify_commit_side_effect=exc)
        assert "verify_head" not in result

    def test_verify_head_warning_on_other_error(self, tmp_path: Path) -> None:
        """GitCommandError unrelated → ok=False, severity=warning (NEVER error)."""
        exc = GitCommandError("verify-commit", 128, stderr="fatal: bad object")
        result, _ = _patch_step6(tmp_path, verify_commit_side_effect=exc)
        check: CheckResult = result["verify_head"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "verify-commit failed"
        assert check["severity"] == "warning"
        assert "error" in check

    def test_verify_head_severity_never_error(self, tmp_path: Path) -> None:
        """Generic exception during repo open for verify_head → severity=warning."""
        result, _ = _patch_step6(tmp_path, repo_open_side_effect=RuntimeError("boom"))
        check: CheckResult = result["verify_head"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["severity"] == "warning"


class TestOverallOkUnaffectedByAuxiliaries:
    """Failing aux checks (warning) must not flip overall_ok to False."""

    def test_failing_agent_does_not_flip_overall_ok(self, tmp_path: Path) -> None:
        """agent_reachable.ok=False (warning) → overall_ok=True if errors pass."""
        result, _ = _patch_step6(tmp_path, which_map={"gpg-connect-agent": None})
        agent: CheckResult = result["agent_reachable"]  # type: ignore[assignment]
        assert agent["ok"] is False
        assert agent["severity"] == "warning"
        assert result["overall_ok"] is True
