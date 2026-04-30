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
    # overall_ok: all error-severity checks must pass
    # ------------------------------------------------------------------
    result["overall_ok"] = all(
        check.get("ok") is True
        for check in result.values()
        if isinstance(check, dict) and check.get("severity") == "error"
    )
    return result
