"""Timeout-bounded git calls through subprocess.

GitPython is the default for git in this package. Network git (``push``,
``ls-remote``) runs here instead, because it can hang on a dead remote and
GitPython's ``kill_after_timeout`` raises on Windows. Output is scrubbed of
URL credentials before it is returned.

Logging names only the subcommand and the timeout, never the full argv or
output, since either may carry a remote URL with credentials.
"""

import os
import shutil
import subprocess
from pathlib import Path

from mcp_workspace.utils.url_credentials import scrub_credentials

from .core import GIT_NONINTERACTIVE_ENV, GitResult, logger

GIT_NETWORK_TIMEOUT: float = 120.0


class GitOutput(GitResult):
    """Result of a timeout-bounded git call; ``stdout`` is "" on failure to run."""

    stdout: str


def _not_run(error: str) -> GitOutput:
    """Build the result for a git call that did not complete.

    Returns:
        A failed GitOutput with no returncode, stderr or stdout.
    """
    return GitOutput(
        success=False, error=error, returncode=None, stderr=None, stdout=""
    )


def run_git_timed(
    project_dir: Path, *args: str, timeout: float = GIT_NETWORK_TIMEOUT
) -> GitOutput:
    """Run git non-interactively in ``project_dir`` with a hard timeout.

    Args:
        project_dir: Working directory for the git process.
        *args: The git subcommand and its arguments.
        timeout: Seconds before the process is killed.

    Returns:
        GitOutput with scrubbed stdout/stderr; never raises for git failures.
    """
    subcommand = args[0] if args else ""
    logger.debug("run_git_timed: git %s timeout=%s", subcommand, timeout)
    git = shutil.which("git")
    if git is None:
        return _not_run("git not found on PATH")
    try:
        proc = subprocess.run(  # noqa: S603
            [git, *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
            cwd=project_dir,
            env={**os.environ, **GIT_NONINTERACTIVE_ENV},
        )
    except subprocess.TimeoutExpired:
        return _not_run(f"git {subcommand} timed out after {timeout:g} s")
    except OSError as e:
        return _not_run(f"git {subcommand} could not run: {e}")
    ok = proc.returncode == 0
    return GitOutput(
        success=ok,
        error=None if ok else f"git {subcommand} failed (exit {proc.returncode})",
        returncode=proc.returncode,
        stderr=scrub_credentials(proc.stderr or ""),
        stdout=scrub_credentials(proc.stdout or ""),
    )
