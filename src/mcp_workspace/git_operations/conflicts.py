"""Conflict inspection and resolution for a stopped rebase or merge."""

from pathlib import Path
from typing import Optional

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from .core import (
    ConflictBlobEntry,
    ConflictBlobInfoResult,
    ConflictStageResult,
    GitResult,
    TreeListing,
    is_option_like,
    logger,
    open_repo_for_query,
    run_git_raw,
    safe_repo_context,
)
from .porcelain_parsers import parse_ls_files_u_z, parse_ls_tree_z

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
    """  # noqa: DOC502  # ValueError propagates from open_repo_for_query
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
    """Read a blob's raw bytes, trailing newline included.

    Returns:
        ``(returncode, stdout, stderr)`` from ``git cat-file blob``.
    """
    return run_git_raw(repo, "cat_file", "blob", sha, strip_newline=False)


def _blob_info_failure(
    error: str, returncode: Optional[int] = None, stderr: Optional[str] = None
) -> ConflictBlobInfoResult:
    """Build a failed ConflictBlobInfoResult.

    Returns:
        A result with ``success`` False and no entries.
    """
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
    """Build a ConflictStageResult.

    Returns:
        A result populated from the arguments.
    """
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


def resolve_take_theirs_or_remove(project_dir: Path, path: str) -> GitResult:
    """Take the feature side (stage 3) and stage it; remove the path if absent.

    During a rebase "theirs" (stage 3) is the commit being replayed, i.e. the
    feature branch. If stage 3 exists the path is checked out from it and
    staged; otherwise (the feature side deleted it) the path is removed from
    the index and the working tree. ``path`` is matched literally.

    Args:
        project_dir: Path to the project directory containing the git repository
        path: Repo-relative path as returned by ``list_unmerged_paths``

    Returns:
        GitResult. A path with no unmerged entries, a non-repository or any
        git failure is ``success=False``.
    """
    logger.debug("Resolving %s with theirs in %s", path, project_dir)

    try:
        with safe_repo_context(project_dir) as repo:
            returncode, stdout, stderr = run_git_raw(
                repo, "ls_files", "-u", "-z", "--", path, literal_paths=True
            )
            if returncode != 0:
                logger.debug("git ls-files -u failed (exit %s): %s", returncode, stderr)
                return {
                    "success": False,
                    "error": f"git ls-files -u failed (exit {returncode})",
                    "returncode": returncode,
                    "stderr": stderr,
                }

            stages = {
                entry.stage
                for entry in parse_ls_files_u_z(stdout)
                if entry.path == path
            }
            if not stages:
                return {
                    "success": False,
                    "error": f"Path is not unmerged: {path}",
                    "returncode": None,
                    "stderr": None,
                }

            commands: list[tuple[str, ...]]
            if 3 in stages:
                commands = [("checkout", "--theirs"), ("add",)]
            else:
                commands = [("rm", "-q")]
            for command, *options in commands:
                returncode, _, stderr = run_git_raw(
                    repo, command, *options, "--", path, literal_paths=True
                )
                if returncode != 0:
                    logger.debug(
                        "git %s failed (exit %s): %s", command, returncode, stderr
                    )
                    return {
                        "success": False,
                        "error": f"git {command} failed (exit {returncode})",
                        "returncode": returncode,
                        "stderr": stderr,
                    }
    except (InvalidGitRepositoryError, NoSuchPathError):
        logger.debug("Not a git repository: %s", project_dir)
        return {
            "success": False,
            "error": f"Not a git repository: {project_dir}",
            "returncode": None,
            "stderr": None,
        }

    return {"success": True, "error": None, "returncode": returncode, "stderr": stderr}


def _tree_failure(
    error: str, returncode: Optional[int] = None, stderr: Optional[str] = None
) -> TreeListing:
    """Build a failed TreeListing.

    Returns:
        A listing with ``success`` False and no entries.
    """
    return {
        "success": False,
        "error": error,
        "returncode": returncode,
        "stderr": stderr,
        "entries": [],
    }


def list_tree(project_dir: Path, ref: str, path: str) -> TreeListing:
    """List the direct contents of directory ``path`` at ``ref``.

    Runs ``git ls-tree -z <ref> -- <path>/``; no recursion, and ``path`` is
    matched literally. Reads the ref's tree, so it works for any ref (e.g.
    ``origin/main``) whatever is checked out.

    Args:
        project_dir: Path to the project directory containing the git repository
        ref: Commit-ish to read
        path: Repo-relative directory, with or without a trailing slash

    Returns:
        TreeListing with repo-relative entry paths (e.g. ``pr_info/a.md``). A
        path absent at ``ref`` is ``success=True`` with no entries. An empty
        or option-like ref, a non-repository or any git failure (e.g. an
        unknown ref) is ``success=False``.
    """
    logger.debug("Listing %s at %s in %s", path, ref, project_dir)

    if not ref or is_option_like(ref):
        return _tree_failure(f"Invalid ref: {ref!r}")

    try:
        with safe_repo_context(project_dir) as repo:
            returncode, stdout, stderr = run_git_raw(
                repo,
                "ls_tree",
                "-z",
                ref,
                "--",
                path.rstrip("/") + "/",
                literal_paths=True,
            )
    except (InvalidGitRepositoryError, NoSuchPathError):
        logger.debug("Not a git repository: %s", project_dir)
        return _tree_failure(f"Not a git repository: {project_dir}")

    if returncode != 0:
        logger.debug("git ls-tree failed (exit %s): %s", returncode, stderr)
        return _tree_failure(
            f"git ls-tree failed (exit {returncode})", returncode, stderr
        )
    return {
        "success": True,
        "error": None,
        "returncode": returncode,
        "stderr": stderr,
        "entries": parse_ls_tree_z(stdout),
    }
