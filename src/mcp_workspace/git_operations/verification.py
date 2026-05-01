"""Local git environment and signing health verification.

Provides verify_git() which runs structured checks against the local git
configuration, including commit-signing setup. Returns per-check results.

Note on logging: ``@log_function_call`` from ``mcp_coder_utils`` logs both
parameter and return values at debug level (the `_log_call_start` /
`_log_call_success` helpers serialise them via json.dumps). To honour
Decision #11 — which forbids logging signing-key IDs / fingerprints /
signed payload contents — this module deliberately avoids that decorator
and uses targeted manual ``logger.debug`` calls that omit sensitive values.
"""

import logging
import shutil
import subprocess  # noqa: S404
from pathlib import Path
from typing import Literal, Optional

from git import Repo
from git.exc import GitCommandError

from ._signing_helpers import (
    PROBE_PAYLOAD,
    CheckResult,
    build_signing_consistency_result,
    build_signing_intent_result,
    build_signing_key_result,
    build_user_identity_result,
    classify_signing_format,
    signing_binary_install_hint,
)
from .core import safe_repo_context
from .repository_status import is_git_repository

logger = logging.getLogger(__name__)

__all__ = ["CheckResult", "PROBE_PAYLOAD", "verify_git"]


def _get_config(repo: Repo, key: str, *extra_args: str) -> Optional[str]:
    """Read a git config value; return None if the key is unset.

    Manually logs only the requested key (never the value) to honour
    Decision #11: signing-related config values must never be logged.
    """
    logger.debug("_get_config: reading key=%s", key)
    try:
        value = repo.git.config("--get", key, *extra_args)
    except GitCommandError:
        return None
    stripped = str(value).strip()
    return stripped or None


def _run(args: list[str], timeout: float) -> "subprocess.CompletedProcess[str]":
    """Run an external binary with subprocess discipline.

    Uses ``stdin=DEVNULL``, captures output, never raises on non-zero exit,
    and enforces an explicit timeout. The single chokepoint for direct
    subprocess use in this package.

    Manually logs only the binary name (args[0]) at debug level — never
    the full argv, since callers may pass signing key IDs.
    """
    if args:
        logger.debug("_run: invoking binary=%s timeout=%s", args[0], timeout)
    return subprocess.run(  # noqa: S603
        args,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _run_with_input(
    args: list[str],
    *,
    input: str,  # pylint: disable=redefined-builtin
    timeout: float,
) -> "subprocess.CompletedProcess[str]":
    """Run an external binary feeding ``input`` to its stdin.

    Same discipline as :func:`_run` (``capture_output=True``, ``text=True``,
    ``check=False``, explicit timeout) but accepts a string fed to stdin.
    Used only by the Tier 3 ``actual_signature`` deep probe.

    Manually logs only the binary name; never the argv (which contains the
    signing key id) and never ``input`` or the resulting signed output.
    """
    if args:
        logger.debug("_run_with_input: invoking binary=%s timeout=%s", args[0], timeout)
    return subprocess.run(  # noqa: S603
        args,
        input=input,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def verify_git(
    project_dir: Path,
    *,
    actually_sign: bool = False,
) -> dict[str, object]:
    """Verify local git environment and (if configured) signing setup.

    Args:
        project_dir: Path to the project directory containing a git repository.
        actually_sign: If True, run the Tier 3 deep-probe sign attempt.

    Returns:
        Dict with ``overall_ok`` bool plus per-check ``CheckResult`` entries.

    Note: parameter/return values are not auto-logged — see module docstring.
    """
    logger.debug(
        "verify_git: entering project_dir=%s actually_sign=%s",
        project_dir,
        actually_sign,
    )
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
        result["user_identity"] = build_user_identity_result(name, email)
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
    git_repo_ok = isinstance(git_repo_check, dict) and git_repo_check.get("ok") is True
    if git_repo_ok:
        with safe_repo_context(project_dir) as repo:
            for flag in (
                "commit.gpgsign",
                "tag.gpgsign",
                "rebase.gpgSign",
                "push.gpgSign",
            ):
                flags_truthy[flag] = _get_config(repo, flag, "--type=bool") == "true"

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
    else:
        result["signing_intent"] = build_signing_intent_result(flags_truthy)
        if not signing_intent_detected:
            result["signing_consistency"] = CheckResult(
                ok=True,
                value="not applicable",
                severity="warning",
            )
        else:
            result["signing_consistency"] = build_signing_consistency_result(
                flags_truthy
            )

    # ------------------------------------------------------------------
    # Tier 2: config-only checks (gated on signing_intent_detected)
    # ------------------------------------------------------------------
    signing_format_resolved: str = "openpgp"
    signing_key: Optional[str] = None
    gpg_program_raw: Optional[str] = None
    allowed_signers_raw: Optional[str] = None
    if signing_intent_detected:
        with safe_repo_context(project_dir) as repo:
            raw_format = _get_config(repo, "gpg.format")
            signing_key = _get_config(repo, "user.signingkey")
            gpg_program_raw = _get_config(repo, "gpg.program")
            allowed_signers_raw = _get_config(repo, "gpg.ssh.allowedSignersFile")

        signing_format_resolved, result["signing_format"] = classify_signing_format(
            raw_format
        )
        result["signing_key"] = build_signing_key_result(
            signing_key, flags_truthy["commit.gpgsign"]
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
            if signing_binary_path is None:
                result["signing_binary"] = CheckResult(
                    ok=False,
                    value="not found",
                    severity="error",
                    error=f"binary for {signing_format_resolved} not on PATH",
                    install_hint=signing_binary_install_hint(signing_format_resolved),
                )
            else:
                try:
                    proc = _run([signing_binary_path, "--version"], timeout=5)
                except subprocess.TimeoutExpired:
                    logger.debug(
                        "signing_binary --version timed out for format=%s",
                        signing_format_resolved,
                    )
                    result["signing_binary"] = CheckResult(
                        ok=False,
                        value=f"{signing_format_resolved} binary timed out",
                        severity="error",
                        error=(
                            f"{signing_format_resolved} --version timed out " "(>5s)"
                        ),
                    )
                    signing_binary_path = None
                else:
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
                err_text = (proc.stderr or proc.stdout).strip()[:500] or "no match"
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

        # ----------------------------------------------------------
        # Tier 2: agent_reachable (openpgp / x509 only)
        # ----------------------------------------------------------
        if signing_format_resolved in ("openpgp", "x509"):
            agent_path = shutil.which("gpg-connect-agent")
            if agent_path is None:
                result["agent_reachable"] = CheckResult(
                    ok=False,
                    value="not found",
                    severity="warning",
                    error="gpg-connect-agent not on PATH",
                    install_hint=(
                        "Install Gpg4win (Windows) or GnuPG (Linux/Mac); "
                        "the agent ships with the toolkit."
                    ),
                )
            else:
                try:
                    proc = _run([agent_path, "/bye"], timeout=5)
                except subprocess.TimeoutExpired:
                    logger.debug("gpg-connect-agent /bye timed out")
                    result["agent_reachable"] = CheckResult(
                        ok=False,
                        value="gpg-agent unreachable (timeout)",
                        severity="warning",
                        error="gpg-connect-agent /bye timed out (>5s)",
                    )
                else:
                    if proc.returncode == 0:
                        result["agent_reachable"] = CheckResult(
                            ok=True, value="reachable", severity="warning"
                        )
                    else:
                        result["agent_reachable"] = CheckResult(
                            ok=False,
                            value="unreachable",
                            severity="warning",
                            error=(proc.stderr or proc.stdout).strip()[:500],
                        )

        # ----------------------------------------------------------
        # Tier 2: allowed_signers (ssh only)
        # ----------------------------------------------------------
        if signing_format_resolved == "ssh":
            if allowed_signers_raw is None:
                result["allowed_signers"] = CheckResult(
                    ok=False,
                    value="not configured",
                    severity="warning",
                    error="gpg.ssh.allowedSignersFile is not set",
                    install_hint=(
                        "Set gpg.ssh.allowedSignersFile to the path of an "
                        "allowed-signers file."
                    ),
                )
            elif not Path(allowed_signers_raw).is_file():
                result["allowed_signers"] = CheckResult(
                    ok=False,
                    value=f"file missing: {allowed_signers_raw}",
                    severity="warning",
                    error=f"allowed signers file does not exist: {allowed_signers_raw}",
                )
            else:
                result["allowed_signers"] = CheckResult(
                    ok=True, value=allowed_signers_raw, severity="warning"
                )

        # ----------------------------------------------------------
        # Tier 2: verify_head (all formats)
        # ----------------------------------------------------------
        try:
            with safe_repo_context(project_dir) as repo:
                if repo.head.is_valid():
                    try:
                        repo.git.verify_commit("HEAD")
                        result["verify_head"] = CheckResult(
                            ok=True,
                            value="HEAD signature valid",
                            severity="warning",
                        )
                    except GitCommandError as exc:
                        stderr = (getattr(exc, "stderr", "") or "").lower()
                        if "no signature" in stderr or "not signed" in stderr:
                            logger.debug("verify_head skipped: HEAD is unsigned")
                        else:
                            result["verify_head"] = CheckResult(
                                ok=False,
                                value="verify-commit failed",
                                severity="warning",
                                error=str(exc)[:500],
                            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("verify_head: outer failure: %s", exc)
            result["verify_head"] = CheckResult(
                ok=False,
                value="verify-commit failed",
                severity="warning",
                error=str(exc)[:500],
            )

        # ----------------------------------------------------------
        # Tier 3: actual_signature (opt-in deep probe)
        # ----------------------------------------------------------
        if actually_sign:
            if signing_format_resolved in ("ssh", "x509"):
                result["actual_signature"] = CheckResult(
                    ok=True,
                    value="not implemented for ssh/x509",
                    severity="warning",
                )
            else:
                signing_key_check = result.get("signing_key")
                signing_key_ok = (
                    isinstance(signing_key_check, dict)
                    and signing_key_check.get("ok") is True
                )
                if not signing_key_ok:
                    result["actual_signature"] = CheckResult(
                        ok=False,
                        value="cannot probe: user.signingkey unavailable",
                        severity="error",
                        error="user.signingkey unavailable",
                    )
                elif signing_binary_path is None:
                    result["actual_signature"] = CheckResult(
                        ok=False,
                        value="cannot probe: gpg binary unavailable",
                        severity="error",
                        error="signing binary unavailable",
                    )
                else:
                    # signing_key_ok is True only when signing_key is not None
                    # (build_signing_key_result returns ok=False otherwise);
                    # narrow for mypy.
                    assert signing_key is not None
                    try:
                        proc = _run_with_input(
                            [
                                signing_binary_path,
                                "--clearsign",
                                "--local-user",
                                signing_key,
                            ],
                            input=PROBE_PAYLOAD,
                            timeout=15,
                        )
                    except subprocess.TimeoutExpired:
                        logger.debug("actual_signature --clearsign timed out")
                        result["actual_signature"] = CheckResult(
                            ok=False,
                            value="signing timed out (>15s)",
                            severity="error",
                            error="gpg --clearsign exceeded 15s timeout",
                        )
                    else:
                        if (
                            proc.returncode == 0
                            and "BEGIN PGP SIGNED MESSAGE" in proc.stdout
                        ):
                            logger.debug("signature produced")
                            result["actual_signature"] = CheckResult(
                                ok=True,
                                value="probe signed successfully",
                                severity="error",
                            )
                        else:
                            logger.debug(
                                "signature failed: returncode=%s",
                                proc.returncode,
                            )
                            result["actual_signature"] = CheckResult(
                                ok=False,
                                value="signing failed",
                                severity="error",
                                error=(proc.stderr or "").strip()[:500],
                            )

    # ------------------------------------------------------------------
    # overall_ok: all error-severity checks must pass
    # ------------------------------------------------------------------
    result["overall_ok"] = all(
        check.get("ok") is True
        for check in result.values()
        if isinstance(check, dict) and check.get("severity") == "error"
    )
    logger.debug("verify_git: exiting overall_ok=%s", result["overall_ok"])
    return result
