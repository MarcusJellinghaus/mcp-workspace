"""Rebase primitives: conflict probing."""

import re
from pathlib import Path
from typing import Literal, Optional

from git import Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError

from .core import RebaseProbe, is_option_like, logger, run_git_raw, safe_repo_context
from .porcelain_parsers import parse_merge_tree_z

# First git release with `merge-tree --write-tree`
_MERGE_TREE_MIN_VERSION = (2, 38)


def _git_version(repo: Repo) -> tuple[int, int]:
    """Return git's ``(major, minor)`` version, e.g. ``(2, 43)``.

    Parses ``git version 2.43.0.windows.1``; unparseable output is ``(0, 0)``.
    """
    match = re.search(r"(\d+)\.(\d+)", repo.git.version())
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def _probe_result(
    status: Literal["conflict", "clean", "unsupported", "error"],
    error: Optional[str],
    returncode: Optional[int] = None,
    stderr: Optional[str] = None,
    files: Optional[list[str]] = None,
) -> RebaseProbe:
    """Build a RebaseProbe; ``success`` is derived from ``status``."""
    return {
        "success": status == "clean",
        "error": error,
        "returncode": returncode,
        "stderr": stderr,
        "status": status,
        "files": files or [],
    }


def probe_rebase_conflicts(project_dir: Path, base_ref: str) -> RebaseProbe:
    """Predict whether rebasing HEAD onto ``base_ref`` would conflict.

    Runs ``git merge-tree --write-tree`` (git 2.38+), which touches neither
    the working tree nor the index. A three-way merge of the two tips is an
    approximation of a commit-by-commit rebase.

    Args:
        project_dir: Path to the project directory containing the git repository
        base_ref: Ref or sha to rebase onto; must not start with ``-``

    Returns:
        RebaseProbe with ``status``:
        ``clean`` (``success=True``), ``conflict`` (``error=None``, conflicted
        paths in ``files``), ``unsupported`` (git older than 2.38) or
        ``error`` (bad ref, non-repository, any other git failure).
    """
    logger.debug("Probing rebase conflicts onto %s in %s", base_ref, project_dir)

    if is_option_like(base_ref):
        return _probe_result("error", f"Invalid ref: {base_ref}")

    try:
        with safe_repo_context(project_dir) as repo:
            returncode, stdout, stderr = run_git_raw(
                repo,
                "merge_tree",
                "--write-tree",
                "--name-only",
                "--no-messages",
                "-z",
                base_ref,
                "HEAD",
            )
            # Only an unexpected exit code needs the (extra) version call
            too_old = (
                returncode not in (0, 1)
                and _git_version(repo) < _MERGE_TREE_MIN_VERSION
            )
    except (InvalidGitRepositoryError, NoSuchPathError):
        logger.debug("Not a git repository: %s", project_dir)
        return _probe_result("error", f"Not a git repository: {project_dir}")

    if returncode == 0:
        return _probe_result("clean", None, returncode, stderr)

    if returncode == 1:
        tree, files = parse_merge_tree_z(stdout)
        if tree:
            return _probe_result("conflict", None, returncode, stderr, files)
        logger.debug("git merge-tree failed (exit 1): %s", stderr)
        return _probe_result(
            "error", "git merge-tree failed (exit 1)", returncode, stderr
        )

    logger.debug("git merge-tree failed (exit %s): %s", returncode, stderr)
    if too_old:
        return _probe_result(
            "unsupported",
            "git merge-tree --write-tree requires git 2.38 or later",
            returncode,
            stderr,
        )
    return _probe_result(
        "error", f"git merge-tree failed (exit {returncode})", returncode, stderr
    )
