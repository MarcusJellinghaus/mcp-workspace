"""Local git environment and signing health verification.

Provides verify_git() which runs structured checks against the local git
configuration, including commit-signing setup. Returns per-check results.
"""

import logging
import shutil
import subprocess  # noqa: S404
from pathlib import Path
from typing import Literal, NotRequired, Optional, TypedDict

from git import Repo
from git.exc import GitCommandError
from mcp_coder_utils.log_utils import log_function_call

from .core import safe_repo_context
from .repository_status import is_git_repository

logger = logging.getLogger(__name__)


class CheckResult(TypedDict):
    """Result of a single verification check."""

    ok: bool
    value: str
    severity: Literal["error", "warning"]
    error: NotRequired[str]
    install_hint: NotRequired[str]


@log_function_call
def _get_config(repo: Repo, key: str, *extra_args: str) -> Optional[str]:
    """Read a git config value; return None if the key is unset."""
    try:
        value = repo.git.config("--get", key, *extra_args)
    except GitCommandError:
        return None
    stripped = str(value).strip()
    return stripped or None


@log_function_call
def _run(args: list[str], timeout: float) -> "subprocess.CompletedProcess[str]":
    """Run an external binary with subprocess discipline.

    Uses ``stdin=DEVNULL``, captures output, never raises on non-zero exit,
    and enforces an explicit timeout. The single chokepoint for direct
    subprocess use in this package.
    """
    return subprocess.run(  # noqa: S603
        args,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


@log_function_call
def verify_git(
    project_dir: Path,
    *,
    actually_sign: bool = False,  # pylint: disable=unused-argument
) -> dict[str, object]:
    """Verify local git environment and (if configured) signing setup.

    Args:
        project_dir: Path to the project directory containing a git repository.
        actually_sign: If True, run the Tier 3 deep-probe sign attempt.

    Returns:
        Dict with ``overall_ok`` bool plus per-check ``CheckResult`` entries.
    """
    result: dict[str, object] = {}

    # ------------------------------------------------------------------
    # Tier 1: baseline checks
    # ------------------------------------------------------------------

    # git_binary
    git_path = shutil.which("git")
    if git_path is None:
        result["git_binary"] = CheckResult(
            ok=False,
            value="not found",
            severity="error",
            error="git not on PATH",
            install_hint="Install git from https://git-scm.com/downloads",
        )
    else:
        logger.debug("Resolved git binary at %s", git_path)
        proc = _run([git_path, "--version"], timeout=5)
        if proc.returncode == 0 and "git version" in proc.stdout:
            result["git_binary"] = CheckResult(
                ok=True,
                value=proc.stdout.strip(),
                severity="error",
            )
        else:
            result["git_binary"] = CheckResult(
                ok=False,
                value="found but not runnable",
                severity="error",
                error=(proc.stderr or "").strip()[:500],
            )

    # git_repo
    if is_git_repository(project_dir):
        result["git_repo"] = CheckResult(
            ok=True,
            value=str(project_dir),
            severity="error",
        )
    else:
        result["git_repo"] = CheckResult(
            ok=False,
            value="not a git repo",
            severity="error",
            error=f"{project_dir} is not a git repository",
        )

    # user_identity
    git_repo_check = result["git_repo"]
    if isinstance(git_repo_check, dict) and git_repo_check.get("ok"):
        with safe_repo_context(project_dir) as repo:
            name = _get_config(repo, "user.name")
            email = _get_config(repo, "user.email")
        missing = [
            label
            for label, value in (("user.name", name), ("user.email", email))
            if value is None
        ]
        if missing:
            result["user_identity"] = CheckResult(
                ok=False,
                value=f"missing: {', '.join(missing)}",
                severity="error",
                error=f"git config missing: {', '.join(missing)}",
                install_hint=(
                    "Set user.name and user.email via "
                    "'git config --global user.{name,email}'"
                ),
            )
        else:
            result["user_identity"] = CheckResult(
                ok=True,
                value=f"{name} <{email}>",
                severity="error",
            )
    else:
        result["user_identity"] = CheckResult(
            ok=False,
            value="unknown",
            severity="error",
            error="repository not accessible",
        )

    # ------------------------------------------------------------------
    # Tier 1: signing detection
    # ------------------------------------------------------------------
    flags_truthy: dict[str, bool] = {}
    git_repo_ok = (
        isinstance(git_repo_check, dict) and git_repo_check.get("ok") is True
    )
    if git_repo_ok:
        with safe_repo_context(project_dir) as repo:
            for flag in (
                "commit.gpgsign",
                "tag.gpgsign",
                "rebase.gpgSign",
                "push.gpgSign",
            ):
                flags_truthy[flag] = (
                    _get_config(repo, flag, "--type=bool") == "true"
                )

    signing_intent_detected = any(flags_truthy.values())
    logger.debug("signing intent detected: %s", signing_intent_detected)

    if not git_repo_ok:
        result["signing_intent"] = CheckResult(
            ok=False,
            value="unknown",
            severity="warning",
            error="repository not accessible",
        )
        result["signing_consistency"] = CheckResult(
            ok=False,
            value="unknown",
            severity="warning",
            error="repository not accessible",
        )
    elif not signing_intent_detected:
        result["signing_intent"] = CheckResult(
            ok=True,
            value="not configured",
            severity="warning",
            install_hint=(
                "Enable signing with 'git config --global commit.gpgsign true' "
                "(and set user.signingkey)."
            ),
        )
        result["signing_consistency"] = CheckResult(
            ok=True,
            value="not applicable",
            severity="warning",
        )
    else:
        enabled = [k for k, v in flags_truthy.items() if v]
        result["signing_intent"] = CheckResult(
            ok=True,
            value=f"detected: {', '.join(enabled)}",
            severity="warning",
        )

        if not flags_truthy.get("commit.gpgsign"):
            result["signing_consistency"] = CheckResult(
                ok=True,
                value="not applicable",
                severity="warning",
            )
        else:
            rebase_label = (
                "rebase ok"
                if flags_truthy["rebase.gpgSign"]
                else "rebase.gpgSign unset"
            )
            tag_label = (
                "tag ok"
                if flags_truthy["tag.gpgsign"]
                else "tag.gpgsign unset"
            )
            consistency_errors: list[str] = []
            if not flags_truthy["rebase.gpgSign"]:
                consistency_errors.append(
                    "rebase.gpgSign unset → rebased commits unsigned on git < 2.36"
                )
            if not flags_truthy["tag.gpgsign"]:
                consistency_errors.append(
                    "tag.gpgsign unset → tags will be unsigned"
                )
            consistency = CheckResult(
                ok=not consistency_errors,
                value=f"{rebase_label}; {tag_label}",
                severity="warning",
            )
            if consistency_errors:
                consistency["error"] = "; ".join(consistency_errors)
            result["signing_consistency"] = consistency

    # ------------------------------------------------------------------
    # Tier 2: config-only checks (gated on signing_intent_detected)
    # ------------------------------------------------------------------
    signing_format_resolved: str = "openpgp"
    signing_key: Optional[str] = None
    gpg_program_raw: Optional[str] = None
    if signing_intent_detected:
        with safe_repo_context(project_dir) as repo:
            raw_format = _get_config(repo, "gpg.format")
            signing_key = _get_config(repo, "user.signingkey")
            gpg_program_raw = _get_config(repo, "gpg.program")

        if raw_format is None:
            signing_format_resolved = "openpgp"
            result["signing_format"] = CheckResult(
                ok=True,
                value="openpgp (default)",
                severity="error",
            )
        elif raw_format in ("openpgp", "ssh", "x509"):
            signing_format_resolved = raw_format
            result["signing_format"] = CheckResult(
                ok=True,
                value=raw_format,
                severity="error",
            )
        else:
            signing_format_resolved = "openpgp"
            result["signing_format"] = CheckResult(
                ok=False,
                value=f"unknown: {raw_format}",
                severity="error",
                error=(
                    f"gpg.format must be openpgp, ssh, or x509 "
                    f"(got '{raw_format}')"
                ),
            )

        if signing_key is None:
            sev: Literal["error", "warning"] = (
                "error" if flags_truthy["commit.gpgsign"] else "warning"
            )
            result["signing_key"] = CheckResult(
                ok=False,
                value="not set",
                severity=sev,
                error="user.signingkey is not configured",
                install_hint=(
                    "Set user.signingkey via "
                    "'git config --global user.signingkey <ID>'"
                ),
            )
        else:
            result["signing_key"] = CheckResult(
                ok=True,
                value="configured",
                severity="error",
            )

        # ----------------------------------------------------------
        # Tier 2: signing_binary
        # ----------------------------------------------------------
        signing_binary_path: Optional[str] = None

        if signing_format_resolved == "openpgp":
            if gpg_program_raw is not None:
                if Path(gpg_program_raw).is_file():
                    signing_binary_path = gpg_program_raw
                    logger.debug("Using gpg.program: %s", gpg_program_raw)
                else:
                    result["signing_binary"] = CheckResult(
                        ok=False,
                        value=f"configured but missing: {gpg_program_raw}",
                        severity="error",
                        error=(
                            f"gpg.program points to non-existent file: "
                            f"{gpg_program_raw}"
                        ),
                        install_hint=(
                            "Set gpg.program to a valid path or unset it "
                            "to use the system PATH lookup."
                        ),
                    )
            if signing_binary_path is None and "signing_binary" not in result:
                signing_binary_path = shutil.which("gpg")
        elif signing_format_resolved == "ssh":
            signing_binary_path = shutil.which("ssh-keygen")
        elif signing_format_resolved == "x509":
            signing_binary_path = shutil.which("gpgsm")

        if "signing_binary" not in result:
            install_hints = {
                "openpgp": (
                    "Install Gpg4win (Windows) or 'gpg' (Linux/Mac), "
                    "or set gpg.format=ssh"
                ),
                "ssh": "Install OpenSSH >= 8.0 (provides ssh-keygen)",
                "x509": (
                    "Install gpgsm (part of GnuPG) or set gpg.format=openpgp"
                ),
            }
            if signing_binary_path is None:
                result["signing_binary"] = CheckResult(
                    ok=False,
                    value="not found",
                    severity="error",
                    error=f"binary for {signing_format_resolved} not on PATH",
                    install_hint=install_hints.get(signing_format_resolved, ""),
                )
            else:
                proc = _run([signing_binary_path, "--version"], timeout=5)
                if proc.returncode == 0:
                    first_line = (proc.stdout.splitlines() or [""])[0].strip()
                    result["signing_binary"] = CheckResult(
                        ok=True,
                        value=first_line[:200],
                        severity="error",
                    )
                else:
                    result["signing_binary"] = CheckResult(
                        ok=False,
                        value="not runnable",
                        severity="error",
                        error=(proc.stderr or "").strip()[:500],
                    )
                    signing_binary_path = None

        # ----------------------------------------------------------
        # Tier 2: signing_key_accessible
        # ----------------------------------------------------------
        if signing_key is None:
            key_acc_severity: Literal["error", "warning"] = (
                "error" if flags_truthy["commit.gpgsign"] else "warning"
            )
            result["signing_key_accessible"] = CheckResult(
                ok=False,
                value="cannot probe: user.signingkey not set",
                severity=key_acc_severity,
                error="user.signingkey unset",
            )
        elif signing_binary_path is None:
            result["signing_key_accessible"] = CheckResult(
                ok=False,
                value="cannot probe: signing binary unavailable",
                severity="error",
                error="signing_binary failed",
            )
        elif signing_format_resolved in ("openpgp", "x509"):
            proc = _run(
                [signing_binary_path, "--list-secret-keys", signing_key],
                timeout=5,
            )
            key_ok = proc.returncode == 0 and bool(proc.stdout.strip())
            if key_ok:
                result["signing_key_accessible"] = CheckResult(
                    ok=True, value="found", severity="error"
                )
            else:
                err_text = (
                    (proc.stderr or proc.stdout).strip()[:500] or "no match"
                )
                result["signing_key_accessible"] = CheckResult(
                    ok=False,
                    value="not found",
                    severity="error",
                    error=err_text,
                )
        elif signing_format_resolved == "ssh":
            if Path(signing_key).is_file():
                result["signing_key_accessible"] = CheckResult(
                    ok=True, value="found", severity="error"
                )
            else:
                result["signing_key_accessible"] = CheckResult(
                    ok=False,
                    value="not found",
                    severity="error",
                    error=f"ssh key file not found: {signing_key}",
                )

    # ------------------------------------------------------------------
    # overall_ok: all error-severity checks must pass
    # ------------------------------------------------------------------
    result["overall_ok"] = all(
        check.get("ok") is True
        for check in result.values()
        if isinstance(check, dict) and check.get("severity") == "error"
    )
    return result
