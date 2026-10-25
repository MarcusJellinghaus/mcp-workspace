"""Git commit operations for creating commits."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from .core import (
    GIT_SHORT_HASH_LENGTH,
    CommitResult,
    logger,
    run_git_raw,
    safe_repo_context,
    to_git_paths,
)
from .porcelain_parsers import parse_status_z
from .repository_status import get_staged_changes, is_git_repository

_SIGNING_KEYWORDS = ("gpg", "signing", "secret key", "signing failed")
_STDERR_LOG_LIMIT = 500


def _classify_commit_failure(
    stderr: str,
) -> Literal["signing_failed", "commit_failed"]:
    """Classify a failed ``git commit`` by its stderr.

    Returns:
        ``"signing_failed"`` if stderr mentions signing, else ``"commit_failed"``.
    """
    stderr_lower = stderr.lower()
    if any(kw in stderr_lower for kw in _SIGNING_KEYWORDS):
        return "signing_failed"
    return "commit_failed"


def commit_staged_files(message: str, project_dir: Path) -> CommitResult:
    """Create a commit from currently staged files.

    Args:
        message: Commit message
        project_dir: Path to the project directory containing the git repository

    Returns:
        CommitResult dictionary containing:
        - success: True if commit was created successfully, False otherwise
        - commit_hash: Git commit SHA (first 7 characters) if successful, None otherwise
        - error: Error message if failed, None if successful
        - error_category: One of "signing_failed", "commit_failed",
          "validation_failed", or None on success.

    Note:
        - Only commits currently staged files
        - Requires non-empty commit message (after stripping whitespace)
        - Returns commit hash on success
        - Provides error details on failure
        - Uses existing is_git_repository() for validation
        - Uses get_staged_changes() to verify there's content to commit
        - Uses git porcelain (``repo.git.commit``) so ``commit.gpgsign``,
          ``user.signingkey``, ``gpg.format``, ``gpg.program``, and the
          ``pre-commit`` / ``commit-msg`` hooks are honored. Hooks now run
          by default (the previous plumbing call silently bypassed them).
    """
    logger.debug("Creating commit with message: %s in %s", message, project_dir)

    # Validate inputs
    if not message or not message.strip():
        error_msg = "Commit message cannot be empty or contain only whitespace"
        logger.error(error_msg)
        return {
            "success": False,
            "commit_hash": None,
            "error": error_msg,
            "error_category": "validation_failed",
            "returncode": None,
            "stderr": None,
        }

    if not is_git_repository(project_dir):
        error_msg = f"Directory is not a git repository: {project_dir}"
        logger.error(error_msg)
        return {
            "success": False,
            "commit_hash": None,
            "error": error_msg,
            "error_category": "validation_failed",
            "returncode": None,
            "stderr": None,
        }

    try:
        # Check if there are staged files to commit
        staged_files = get_staged_changes(project_dir)
        if not staged_files:
            error_msg = "No staged files to commit"
            logger.error(error_msg)
            return {
                "success": False,
                "commit_hash": None,
                "error": error_msg,
                "error_category": "validation_failed",
                "returncode": None,
                "stderr": None,
            }

        # Create the commit via git porcelain so signing config and hooks apply
        with safe_repo_context(project_dir) as repo:
            stripped_message = message.strip()

            config_reader = repo.config_reader()
            commit_gpgsign = config_reader.get_value(
                "commit", "gpgsign", default="<unset>"
            )
            gpg_format = config_reader.get_value("gpg", "format", default="<unset>")
            user_signingkey = config_reader.get_value(
                "user", "signingkey", default="<unset>"
            )

            logger.debug(
                "Invoking git commit with args=('-m', %r); "
                "commit.gpgsign=%s, gpg.format=%s, user.signingkey=%s",
                stripped_message,
                commit_gpgsign,
                gpg_format,
                user_signingkey,
            )

            try:
                repo.git.commit("-m", stripped_message)
            except GitCommandError as e:
                category = _classify_commit_failure(str(e.stderr or ""))
                logger.debug(
                    "git commit failed: stderr=%r status=%s command=%r",
                    str(e.stderr or "")[:_STDERR_LOG_LIMIT],
                    e.status,
                    e.command,
                )
                error_msg = f"Git error creating commit: {e}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "commit_hash": None,
                    "error": error_msg,
                    "error_category": category,
                    "returncode": e.status if isinstance(e.status, int) else None,
                    "stderr": str(e.stderr or ""),
                }

            commit_hash = repo.head.commit.hexsha[:GIT_SHORT_HASH_LENGTH]

            logger.debug(
                "Successfully created commit %s with message: %s",
                commit_hash,
                stripped_message,
            )

            return {
                "success": True,
                "commit_hash": commit_hash,
                "error": None,
                "error_category": None,
                # git commit exited 0; its stderr is not captured on success
                "returncode": 0,
                "stderr": None,
            }

    except InvalidGitRepositoryError as e:
        error_msg = f"Git error creating commit: {e}"
        logger.error(error_msg)
        return {
            "success": False,
            "commit_hash": None,
            "error": error_msg,
            "error_category": "validation_failed",
            "returncode": None,
            "stderr": None,
        }


def commit_paths(message: str, paths: list[Path], project_dir: Path) -> CommitResult:
    """Commit the working-tree content of ``paths`` only (``git commit --only``).

    Staged and unstaged changes to other paths stay uncommitted. Paths are
    matched literally (``*``, ``[`` and ``:(`` have no special meaning).

    Args:
        message: Commit message
        paths: Absolute paths, or paths relative to ``project_dir``
        project_dir: Path to the project directory containing the git repository

    Returns:
        CommitResult dictionary containing:
        - success: True if a commit was created
        - commit_hash: Short SHA of the new commit, None on failure
        - error: Error message on failure, None on success
        - error_category: ``"validation_failed"`` for an empty message, empty
          ``paths``, a non-repository, a path outside ``project_dir`` or an
          untracked path; ``"nothing_to_commit"`` when the paths have no
          changes; ``"signing_failed"`` / ``"commit_failed"`` when
          ``git commit`` fails; None on success.
        - returncode / stderr: From the failing git process, None when none ran

    Note:
        ``nothing_to_commit`` is decided by an empty
        ``git status --porcelain -z -- <paths>``, so a path that is neither
        tracked nor on disk is also ``nothing_to_commit``.
    """
    logger.debug("Committing paths %s in %s", paths, project_dir)

    def _failure(
        error: str,
        category: Literal[
            "signing_failed", "commit_failed", "validation_failed", "nothing_to_commit"
        ],
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
    ) -> CommitResult:
        logger.debug("commit_paths failed: %s", error)
        return {
            "success": False,
            "commit_hash": None,
            "error": error,
            "error_category": category,
            "returncode": returncode,
            "stderr": stderr,
        }

    if not message or not message.strip():
        return _failure(
            "Commit message cannot be empty or contain only whitespace",
            "validation_failed",
        )
    if not paths:
        return _failure("No paths given to commit", "validation_failed")

    try:
        with safe_repo_context(project_dir) as repo:
            try:
                rel_paths = to_git_paths(paths, project_dir)
            except ValueError as e:
                return _failure(str(e), "validation_failed")

            rc, out, err = run_git_raw(
                repo,
                "status",
                "--porcelain",
                "-z",
                "--",
                *rel_paths,
                literal_paths=True,
            )
            if rc != 0:
                return _failure(
                    f"git status failed: {err.strip()}", "commit_failed", rc, err
                )

            entries = parse_status_z(out)
            untracked = [
                entry.path
                for entry in entries
                if entry.index_status == entry.worktree_status == "?"
            ]
            if untracked:
                return _failure(
                    f"Untracked paths cannot be committed: {', '.join(untracked)}",
                    "validation_failed",
                )
            if not entries:
                return _failure(
                    "Nothing to commit for the given paths", "nothing_to_commit"
                )

            rc, _, err = run_git_raw(
                repo,
                "commit",
                "--only",
                "-m",
                message.strip(),
                "--",
                *rel_paths,
                literal_paths=True,
            )
            if rc != 0:
                return _failure(
                    f"Git error creating commit: {err.strip()}",
                    _classify_commit_failure(err),
                    rc,
                    err,
                )

            _, head, _ = run_git_raw(repo, "rev_parse", "HEAD")
            commit_hash = head.decode("ascii").strip()[:GIT_SHORT_HASH_LENGTH]
            logger.debug("Created commit %s for paths %s", commit_hash, rel_paths)
            return {
                "success": True,
                "commit_hash": commit_hash,
                "error": None,
                "error_category": None,
                "returncode": rc,
                "stderr": err,
            }
    except (InvalidGitRepositoryError, NoSuchPathError):
        return _failure(
            f"Directory is not a git repository: {project_dir}", "validation_failed"
        )


def get_latest_commit_sha(project_dir: Path) -> Optional[str]:
    """Get the SHA of the current HEAD commit.

    Args:
        project_dir: Path to the git repository

    Returns:
        The full SHA of HEAD, or None if not in a git repository
    """
    try:
        with safe_repo_context(project_dir) as repo:
            return repo.head.commit.hexsha
    except (InvalidGitRepositoryError, GitCommandError, ValueError, OSError):
        return None


def get_head_commit_info(project_dir: Path) -> Optional[tuple[str, datetime]]:
    """Get HEAD's short SHA and committer date in UTC.

    Committer date, not author date: a rebase rewrites the committer date.

    Args:
        project_dir: Path to the git repository

    Returns:
        (short SHA, tz-aware UTC committer datetime), or None if HEAD
        cannot be read.
    """
    try:
        with safe_repo_context(project_dir) as repo:
            commit = repo.head.commit
            return (
                commit.hexsha[:GIT_SHORT_HASH_LENGTH],
                commit.committed_datetime.astimezone(timezone.utc),
            )
    except (InvalidGitRepositoryError, GitCommandError, ValueError, OSError):
        return None
