"""Conflict inspection and resolution for a stopped rebase or merge."""

from pathlib import Path
from typing import Optional

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from .core import (
    ConflictBlobEntry,
    ConflictBlobInfoResult,
    ConflictStageResult,
    logger,
    open_repo_for_query,
    run_git_raw,
    safe_repo_context,
)
from .porcelain_parsers import parse_ls_files_u_z

# Same heuristic as git: a NUL byte in the first 8000 bytes means binary
_BINARY_SNIFF_BYTES = 8000


def list_unmerged_paths(project_dir: Path) -> list[str]:
    """List the paths that have unmerged (conflict) index entries.

    Args:
        project_dir: Path to the project directory containing the git repository

    Returns:
        Repo-relative paths with forward slashes, each listed once, in git's
        order. Empty if nothing is unmerged.

    Raises:
        ValueError: If ``project_dir`` is not a git repository.
        GitCommandError: If ``git ls-files -u`` fails.
    """
    logger.debug("Listing unmerged paths in %s", project_dir)

    with open_repo_for_query(project_dir) as repo:
        returncode, stdout, stderr = run_git_raw(repo, "ls_files", "-u", "-z")

    if returncode != 0:
        raise GitCommandError(["git", "ls-files", "-u", "-z"], returncode, stderr)
    return list(dict.fromkeys(entry.path for entry in parse_ls_files_u_z(stdout)))


def _is_binary(data: bytes) -> bool:
    """Return True if ``data`` looks binary (NUL byte near the start)."""
    return b"\0" in data[:_BINARY_SNIFF_BYTES]


def _read_blob(repo: Repo, sha: str) -> tuple[int, bytes, str]:
    """Read a blob's raw bytes, trailing newline included."""
    return run_git_raw(repo, "cat_file", "blob", sha, strip_newline=False)


def _blob_info_failure(
    error: str, returncode: Optional[int] = None, stderr: Optional[str] = None
) -> ConflictBlobInfoResult:
    """Build a failed ConflictBlobInfoResult."""
    return {
        "success": False,
        "error": error,
        "returncode": returncode,
        "stderr": stderr,
        "entries": [],
    }


def get_conflict_blob_info(project_dir: Path) -> ConflictBlobInfoResult:
    """Describe every unmerged path: which stages exist and whether binary.

    Stage 1 is the merge base, 2 "ours", 3 "theirs". During a rebase, 2 is the
    upstream being rebased onto and 3 the commit being replayed.

    Args:
        project_dir: Path to the project directory containing the git repository

    Returns:
        ConflictBlobInfoResult with ``entries`` sorted by path; a path is binary
        if any of its stages is. Any git failure, or a non-repository, is
        ``success=False`` with no entries.
    """
    logger.debug("Reading conflict blob info in %s", project_dir)

    try:
        with safe_repo_context(project_dir) as repo:
            returncode, stdout, stderr = run_git_raw(repo, "ls_files", "-u", "-z")
            if returncode != 0:
                logger.debug("git ls-files -u failed (exit %s): %s", returncode, stderr)
                return _blob_info_failure(
                    f"git ls-files -u failed (exit {returncode})", returncode, stderr
                )

            stages: dict[str, list[int]] = {}
            binary: dict[str, bool] = {}
            for entry in parse_ls_files_u_z(stdout):
                blob_rc, data, blob_err = _read_blob(repo, entry.sha)
                if blob_rc != 0:
                    logger.debug(
                        "git cat-file blob %s failed (exit %s): %s",
                        entry.sha,
                        blob_rc,
                        blob_err,
                    )
                    return _blob_info_failure(
                        f"git cat-file blob {entry.sha} failed (exit {blob_rc})",
                        blob_rc,
                        blob_err,
                    )
                stages.setdefault(entry.path, []).append(entry.stage)
                binary[entry.path] = binary.get(entry.path, False) or _is_binary(data)
    except (InvalidGitRepositoryError, NoSuchPathError):
        logger.debug("Not a git repository: %s", project_dir)
        return _blob_info_failure(f"Not a git repository: {project_dir}")

    entries: list[ConflictBlobEntry] = [
        {"path": path, "stages": sorted(stages[path]), "is_binary": binary[path]}
        for path in sorted(stages)
    ]
    return {
        "success": True,
        "error": None,
        "returncode": returncode,
        "stderr": stderr,
        "entries": entries,
    }


def _stage_result(
    success: bool,
    error: Optional[str],
    returncode: Optional[int] = None,
    stderr: Optional[str] = None,
    content: Optional[str] = None,
    is_binary: bool = False,
) -> ConflictStageResult:
    """Build a ConflictStageResult."""
    return {
        "success": success,
        "error": error,
        "returncode": returncode,
        "stderr": stderr,
        "content": content,
        "is_binary": is_binary,
    }


def read_conflict_stage(
    project_dir: Path, stage: int, path: str
) -> ConflictStageResult:
    """Read one index stage of an unmerged path.

    Args:
        project_dir: Path to the project directory containing the git repository
        stage: 1 (base), 2 (ours; upstream during a rebase) or 3 (theirs; the
            replayed commit during a rebase)
        path: Repo-relative path as returned by ``list_unmerged_paths``

    Returns:
        ConflictStageResult. ``content`` keeps the blob's trailing newline and
        is decoded as UTF-8 with replacement. An absent side is
        ``(success=True, content=None, is_binary=False)``, a binary blob
        ``(success=True, content=None, is_binary=True)``. An invalid stage, a
        non-repository or any git failure is ``success=False``.
    """
    logger.debug("Reading stage %s of %s in %s", stage, path, project_dir)

    if stage not in (1, 2, 3):
        return _stage_result(False, f"Invalid stage: {stage!r} (expected 1, 2 or 3)")

    try:
        with safe_repo_context(project_dir) as repo:
            returncode, stdout, stderr = run_git_raw(
                repo, "ls_files", "-u", "-z", "--", path, literal_paths=True
            )
            if returncode != 0:
                logger.debug("git ls-files -u failed (exit %s): %s", returncode, stderr)
                return _stage_result(
                    False,
                    f"git ls-files -u failed (exit {returncode})",
                    returncode,
                    stderr,
                )

            match = next(
                (
                    entry
                    for entry in parse_ls_files_u_z(stdout)
                    if entry.path == path and entry.stage == stage
                ),
                None,
            )
            if match is None:
                return _stage_result(True, None, returncode, stderr)

            returncode, data, stderr = _read_blob(repo, match.sha)
    except (InvalidGitRepositoryError, NoSuchPathError):
        logger.debug("Not a git repository: %s", project_dir)
        return _stage_result(False, f"Not a git repository: {project_dir}")

    if returncode != 0:
        logger.debug(
            "git cat-file blob %s failed (exit %s): %s", match.sha, returncode, stderr
        )
        return _stage_result(
            False,
            f"git cat-file blob {match.sha} failed (exit {returncode})",
            returncode,
            stderr,
        )
    if _is_binary(data):
        return _stage_result(True, None, returncode, stderr, is_binary=True)
    return _stage_result(
        True, None, returncode, stderr, content=data.decode("utf-8", "replace")
    )
