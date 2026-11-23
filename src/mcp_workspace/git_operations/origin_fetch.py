"""Fetch a reference project's ``origin``, retrying once.

The fetch only updates remote-tracking refs: it never touches the working
tree, the index or the checked-out branch. Maintenance and auto-gc are
switched off for the call so it does not rewrite the object store.
"""

from pathlib import Path
from typing import NamedTuple

from ._subprocess_git import GitOutput, run_git_timed
from .core import _close_repo_safely, has_origin, open_repo_if_any

FETCH_ARGS: tuple[str, ...] = (
    "-c",
    "maintenance.auto=false",
    "-c",
    "gc.auto=0",
    "fetch",
    "--quiet",
    "--no-recurse-submodules",
    "--no-prune",
    "origin",
)
_ATTEMPTS = 2


class FetchOutcome(NamedTuple):
    """Result of ``fetch_origin``."""

    attempted: bool  # False: not a git repo, or no origin remote
    failure: str | None  # None on success; scrubbed reason otherwise


def has_origin_remote(path: Path) -> bool:
    """Return True if ``path`` itself is a repository with an ``origin`` remote.

    Parent directories are not searched, so a plain folder inside a
    checkout is not a repository here.

    Args:
        path: Folder to check

    Returns:
        True when the repository at ``path`` has a remote named ``origin``.
    """
    repo = open_repo_if_any(path)
    if repo is None:
        return False
    try:
        return has_origin(repo)
    finally:
        _close_repo_safely(repo)


def _failure_reason(out: GitOutput) -> str:
    """Return the first non-empty stderr line, else the result's error."""
    for line in (out["stderr"] or "").splitlines():
        if line.strip():
            return line.strip()
    return out["error"] or "git fetch failed"


def _timed_out(out: GitOutput) -> bool:
    """Return True if the git process was killed on timeout."""
    return out["returncode"] is None and "timed out" in (out["error"] or "")


def fetch_origin(path: Path, timeout: float = 10.0) -> FetchOutcome:
    """Fetch ``origin`` in ``path``, retrying once unless the first try timed out.

    Args:
        path: Folder of the repository
        timeout: Seconds per attempt before git is killed

    Returns:
        ``FetchOutcome(False, None)`` when ``path`` is not a repository or has
        no ``origin``; otherwise ``attempted=True`` with ``failure`` None on
        success or the scrubbed reason of the last failed attempt.
    """
    if not has_origin_remote(path):
        return FetchOutcome(attempted=False, failure=None)
    reason: str | None = None
    for _ in range(_ATTEMPTS):
        out = run_git_timed(path, *FETCH_ARGS, timeout=timeout)
        if out["success"]:
            return FetchOutcome(attempted=True, failure=None)
        reason = _failure_reason(out)
        if _timed_out(out):
            break
    return FetchOutcome(attempted=True, failure=reason)
