"""Rebase primitives: conflict probing and driving a rebase."""

import re
from pathlib import Path
from typing import Literal, Optional

from git import Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError

from .core import (
    GIT_NONINTERACTIVE_ENV,
    GitResult,
    RebaseProbe,
    RebaseResult,
    is_option_like,
    logger,
    open_repo_for_query,
    run_git_raw,
    safe_repo_context,
)
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
    """Build a RebaseProbe; ``success`` is derived from ``status``.

    Returns:
        A RebaseProbe populated from the arguments.
    """
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


def _rebase_dir_exists(repo: Repo) -> bool:
    """Return True if git's rebase state directory exists in ``repo``."""
    git_dir = Path(repo.git_dir)
    return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()


def _rebase_result(
    status: Literal["completed", "stopped_on_conflict", "error"],
    error: Optional[str],
    returncode: Optional[int] = None,
    stderr: Optional[str] = None,
) -> RebaseResult:
    """Build a RebaseResult; ``success`` is derived from ``status``.

    Returns:
        A RebaseResult populated from the arguments.
    """
    return {
        "success": status == "completed",
        "error": error,
        "returncode": returncode,
        "stderr": stderr,
        "status": status,
    }


def is_rebase_in_progress(project_dir: Path) -> bool:
    """Return True if a rebase is in progress in ``project_dir``.

    Checks the repository's own git dir, so worktrees and submodules report
    their own state.

    Raises:
        ValueError: If ``project_dir`` is not a git repository.
    """  # noqa: DOC502  # ValueError propagates from open_repo_for_query
    with open_repo_for_query(project_dir) as repo:
        return _rebase_dir_exists(repo)


def _run_rebase(project_dir: Path, *args: str) -> RebaseResult:
    """Run ``git rebase <args>`` non-interactively and classify the outcome.

    Exit 0 is ``completed``. A nonzero exit is ``stopped_on_conflict`` if git
    left the rebase in progress (a stop with no unmerged paths included),
    otherwise ``error``.

    Returns:
        RebaseResult classified as described above.
    """
    try:
        with safe_repo_context(project_dir) as repo:
            returncode, _, stderr = run_git_raw(
                repo, "rebase", *args, env=GIT_NONINTERACTIVE_ENV
            )
            in_progress = returncode != 0 and _rebase_dir_exists(repo)
    except (InvalidGitRepositoryError, NoSuchPathError):
        logger.debug("Not a git repository: %s", project_dir)
        return _rebase_result("error", f"Not a git repository: {project_dir}")

    if returncode == 0:
        return _rebase_result("completed", None, returncode, stderr)
    if in_progress:
        logger.debug("git rebase %s stopped: %s", " ".join(args), stderr)
        return _rebase_result("stopped_on_conflict", None, returncode, stderr)
    logger.debug(
        "git rebase %s failed (exit %s): %s", " ".join(args), returncode, stderr
    )
    return _rebase_result(
        "error",
        f"git rebase {' '.join(args)} failed (exit {returncode})",
        returncode,
        stderr,
    )


def rebase_start(project_dir: Path, onto_ref: str) -> RebaseResult:
    """Rebase the current branch onto ``onto_ref``.

    No fetch and no auto-abort: a stop leaves the rebase in progress for the
    caller to resolve, continue, skip or abort.

    Args:
        project_dir: Path to the project directory containing the git repository
        onto_ref: Ref or sha to rebase onto; must not start with ``-``

    Returns:
        RebaseResult; ``error`` without running git if ``onto_ref`` is
        option-like, the directory is not a repository, or a rebase is
        already in progress.
    """
    logger.debug("Starting rebase onto %s in %s", onto_ref, project_dir)

    if is_option_like(onto_ref):
        return _rebase_result("error", f"Invalid ref: {onto_ref}")

    try:
        with safe_repo_context(project_dir) as repo:
            already_running = _rebase_dir_exists(repo)
    except (InvalidGitRepositoryError, NoSuchPathError):
        logger.debug("Not a git repository: %s", project_dir)
        return _rebase_result("error", f"Not a git repository: {project_dir}")

    if already_running:
        return _rebase_result("error", "A rebase is already in progress")
    return _run_rebase(project_dir, onto_ref)


def rebase_continue(project_dir: Path) -> RebaseResult:
    """Run ``git rebase --continue``; does not stage anything first.

    Returns:
        RebaseResult; ``stopped_on_conflict`` if the rebase stops again.
    """
    return _run_rebase(project_dir, "--continue")


def rebase_skip(project_dir: Path) -> RebaseResult:
    """Run ``git rebase --skip``, dropping the commit the rebase stopped on.

    Returns:
        RebaseResult; ``stopped_on_conflict`` if the rebase stops again.
    """
    return _run_rebase(project_dir, "--skip")


def rebase_abort(project_dir: Path) -> GitResult:
    """Abort an in-progress rebase; a no-op success if none is running.

    Returns:
        GitResult; ``returncode`` is None when there was nothing to abort.
    """
    logger.debug("Aborting rebase in %s", project_dir)

    try:
        with safe_repo_context(project_dir) as repo:
            if not _rebase_dir_exists(repo):
                return {
                    "success": True,
                    "error": None,
                    "returncode": None,
                    "stderr": None,
                }
            returncode, _, stderr = run_git_raw(
                repo, "rebase", "--abort", env=GIT_NONINTERACTIVE_ENV
            )
    except (InvalidGitRepositoryError, NoSuchPathError):
        logger.debug("Not a git repository: %s", project_dir)
        return {
            "success": False,
            "error": f"Not a git repository: {project_dir}",
            "returncode": None,
            "stderr": None,
        }

    if returncode != 0:
        logger.debug("git rebase --abort failed (exit %s): %s", returncode, stderr)
        return {
            "success": False,
            "error": f"git rebase --abort failed (exit {returncode})",
            "returncode": returncode,
            "stderr": stderr,
        }
    return {"success": True, "error": None, "returncode": returncode, "stderr": stderr}


def reset_hard(project_dir: Path, sha: str) -> GitResult:
    """Run ``git reset --hard <sha>``, e.g. to restore the pre-rebase state.

    Args:
        project_dir: Path to the project directory containing the git repository
        sha: Commit to reset to; must be non-empty and not start with ``-``

    Returns:
        GitResult; ``returncode`` is None when ``sha`` is invalid or the
        directory is not a repository.
    """
    logger.debug("Resetting %s hard to %s", project_dir, sha)

    if not sha or is_option_like(sha):
        return {
            "success": False,
            "error": f"Invalid sha: {sha!r}",
            "returncode": None,
            "stderr": None,
        }

    try:
        with safe_repo_context(project_dir) as repo:
            # Trailing "--" forces sha to be read as a revision, not a path
            returncode, _, stderr = run_git_raw(repo, "reset", "--hard", sha, "--")
    except (InvalidGitRepositoryError, NoSuchPathError):
        logger.debug("Not a git repository: %s", project_dir)
        return {
            "success": False,
            "error": f"Not a git repository: {project_dir}",
            "returncode": None,
            "stderr": None,
        }

    if returncode != 0:
        logger.debug("git reset --hard failed (exit %s): %s", returncode, stderr)
        return {
            "success": False,
            "error": f"git reset --hard failed (exit {returncode})",
            "returncode": returncode,
            "stderr": stderr,
        }
    return {"success": True, "error": None, "returncode": returncode, "stderr": stderr}
