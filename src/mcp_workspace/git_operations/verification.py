"""Local git environment and signing health verification.

Provides verify_git() which runs structured checks against the local git
configuration, including commit-signing setup. Returns per-check results.
"""

import logging
import subprocess  # noqa: S404
from pathlib import Path
from typing import Literal, NotRequired, Optional, TypedDict

from git import Repo
from git.exc import GitCommandError
from mcp_coder_utils.log_utils import log_function_call

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
    project_dir: Path,  # pylint: disable=unused-argument
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
    # Tier 1, Tier 2, Tier 3 sections are added in subsequent steps.
    result["overall_ok"] = True
    return result
