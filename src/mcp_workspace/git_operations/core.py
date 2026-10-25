"""Core utilities and shared infrastructure for git operations."""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal, Optional, Sequence, TypedDict

from git import Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError

# Use same logging pattern as existing modules (see file_operations.py)
logger = logging.getLogger(__name__)

# Constants for git operations
PLACEHOLDER_HASH = "0" * 7
GIT_SHORT_HASH_LENGTH = 7

# Keep git from waiting on a human: no terminal credential prompt, and any
# editor git would open (rebase --continue, commit without -m) exits at once.
# Passed per call via `env=` so nothing leaks into the shared Git object.
GIT_NONINTERACTIVE_ENV: dict[str, str] = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_EDITOR": "true",
}


class GitResult(TypedDict):
    """Base result of a git operation.

    ``success`` is True only when the goal was reached. ``error`` is None for a
    normal-but-not-done outcome (e.g. a rebase stopped on a conflict).
    ``returncode`` and ``stderr`` are None when no git process ran.
    """

    success: bool
    error: Optional[str]
    returncode: Optional[int]
    stderr: Optional[str]


# Type alias for commit result structure
class CommitResult(GitResult):
    """Result of a git commit operation."""

    commit_hash: Optional[str]
    error_category: Optional[
        Literal[
            "signing_failed", "commit_failed", "validation_failed", "nothing_to_commit"
        ]
    ]


class StatusResult(GitResult):
    """Result of a working-tree status query.

    Paths are repo-relative with forward slashes. ``clean`` is never True
    on failure.
    """

    clean: bool
    staged: list[str]
    modified: list[str]
    untracked: list[str]


class RebaseProbe(GitResult):
    """Result of a dry-run rebase conflict probe.

    ``success`` is True only for ``clean``. A ``conflict`` has ``error`` None
    and lists the conflicted repo-relative paths in ``files``.
    """

    status: Literal["conflict", "clean", "unsupported", "error"]
    files: list[str]


class RebaseResult(GitResult):
    """Result of starting or driving a rebase.

    ``success`` is True only for ``completed``. ``stopped_on_conflict`` means
    the rebase stopped and is still in progress, with ``error`` None. That
    includes a stop with no unmerged paths (an empty commit, a hook); use
    ``list_unmerged_paths`` to tell. A failed command is
    ``stopped_on_conflict`` only if git left the rebase in progress,
    otherwise ``error``.
    """

    status: Literal["completed", "stopped_on_conflict", "error"]


class BranchProbe(GitResult):
    """Result of asking origin whether a branch exists.

    ``exists`` is None when origin couldn't answer; ``success`` is True iff
    ``exists`` is True or False.
    """

    exists: Optional[bool]


class RemoteBranchesResult(GitResult):
    """Result of listing the heads on origin.

    ``branches`` is empty on failure; a failure is never a successful empty
    list.
    """

    branches: list[str]


class ConflictBlobEntry(TypedDict):
    """One unmerged path: the index stages present and whether any is binary."""

    path: str
    stages: list[int]  # subset of 1 (base), 2 (ours), 3 (theirs), ascending
    is_binary: bool


class ConflictBlobInfoResult(GitResult):
    """Result of inspecting the blobs of all unmerged paths.

    ``entries`` is sorted by path and empty on failure.
    """

    entries: list[ConflictBlobEntry]


class ConflictStageResult(GitResult):
    """Result of reading one index stage of an unmerged path.

    An absent side (e.g. deleted) is ``success=True, content=None,
    is_binary=False``; a binary blob is ``success=True, content=None,
    is_binary=True``.
    """

    content: Optional[str]
    is_binary: bool


class TreeEntry(TypedDict):
    """One entry of a tree listing; ``path`` is repo-relative."""

    mode: str
    type: str  # "blob" | "tree" | "commit"
    sha: str
    path: str


class TreeListing(GitResult):
    """Result of listing a directory at a ref.

    ``entries`` is empty on failure and for a path absent at the ref.
    """

    entries: list[TreeEntry]


# Type alias for git push result structure
class PushResult(TypedDict):
    """Result of a git push operation."""

    success: bool
    error: Optional[str]


def _close_repo_safely(repo: Repo) -> None:
    """Safely close a GitPython repository to prevent handle leaks on Windows."""
    try:
        # Close any active git command processes
        # pylint: disable=protected-access  # GitPython has no public API for process cleanup
        if hasattr(repo, "git") and hasattr(repo.git, "_proc") and repo.git._proc:
            try:
                if repo.git._proc.poll() is None:  # Process still running
                    repo.git._proc.terminate()
                    import time

                    time.sleep(0.1)
                    if repo.git._proc.poll() is None:  # Still running, force kill
                        repo.git._proc.kill()
            except (OSError, AttributeError):
                pass  # Ignore errors during process cleanup
        # pylint: enable=protected-access

        # Close the repository if it has a close method
        if hasattr(repo, "close"):
            repo.close()

    except (
        AttributeError,
        OSError,
        Exception,
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        # Log but don't raise - cleanup should be best effort
        logger.debug("Error during repository cleanup (non-critical): %s", e)


@contextmanager
def safe_repo_context(project_dir: Path) -> Iterator[Repo]:
    """Context manager for safely handling GitPython repository objects.

    Ensures proper cleanup of repository objects to prevent Windows handle issues.

    Args:
        project_dir: Path to the git repository directory

    Yields:
        Repo: GitPython repository object
    """
    repo = None
    try:
        repo = Repo(project_dir, search_parent_directories=False)
        yield repo
    finally:
        if repo:
            _close_repo_safely(repo)


def run_git_text(repo: Repo, method: str, *args: str) -> str:
    """Run a git method and decode its output as UTF-8.

    Forces UTF-8 decoding of git stdout (GitPython otherwise decodes with the
    OS locale code page, e.g. cp1252 on Windows). GitPython already strips the
    single trailing newline in bytes mode (``strip_newline_in_stdout``), same
    as string mode, so no extra stripping happens here — stripping more would
    drop trailing blank lines from blob content (``show HEAD:<file>``).

    Returns:
        The command's stdout decoded as UTF-8 (invalid bytes replaced).
    """
    raw_bytes = getattr(repo.git, method)(*args, stdout_as_string=False)
    text: str = raw_bytes.decode("utf-8", errors="replace")
    return text


def run_git_raw(
    repo: Repo,
    command: str,
    *args: str,
    env: Optional[dict[str, str]] = None,
    literal_paths: bool = False,
    strip_newline: bool = True,
) -> tuple[int, bytes, str]:
    """Run a git command without raising on a nonzero exit.

    Args:
        repo: Repository to run the command in
        command: GitPython method name (e.g. ``"rev_parse"``, ``"ls_files"``)
        *args: Command-line arguments passed to git
        env: Extra environment variables for this call only
        literal_paths: Set ``GIT_LITERAL_PATHSPECS=1`` so ``*``, ``[`` and
            ``:(`` in paths are matched literally
        strip_newline: Strip the single trailing newline from stdout; pass
            False wherever blob content is returned

    Returns:
        ``(returncode, stdout_bytes, stderr_text)``; stderr is decoded as
        UTF-8 (invalid bytes replaced) if GitPython hands back bytes.
    """
    call_env = dict(env or {})
    if literal_paths:
        call_env["GIT_LITERAL_PATHSPECS"] = "1"
    status, out, err = getattr(repo.git, command)(
        *args,
        with_extended_output=True,
        with_exceptions=False,
        stdout_as_string=False,
        strip_newline_in_stdout=strip_newline,
        env=call_env or None,
    )
    err_text = (
        err.decode("utf-8", errors="replace") if isinstance(err, bytes) else str(err)
    )
    stdout = out if isinstance(out, bytes) else (out or "").encode("utf-8")
    return int(status), stdout, err_text


def is_option_like(value: str) -> bool:
    """Return True if a caller-supplied ref/sha would be parsed as an option."""
    return value.startswith("-")


def to_git_paths(paths: Sequence[Path], project_dir: Path) -> list[str]:
    """Convert absolute or project-relative paths to repo-relative git paths.

    Args:
        paths: Absolute paths, or paths relative to ``project_dir``
        project_dir: Repository working directory

    Returns:
        Repo-relative paths using forward slashes, in input order.

    Raises:
        ValueError: If a path lies outside ``project_dir``.
    """
    base = project_dir.resolve()
    result: list[str] = []
    for path in paths:
        absolute = path if path.is_absolute() else project_dir / path
        try:
            result.append(_normalize_git_path(absolute.resolve(), base))
        except ValueError:
            raise ValueError(f"Path is outside the project directory: {path}") from None
    return result


@contextmanager
def open_repo_for_query(project_dir: Path) -> Iterator[Repo]:
    """Open a repository for a plain-value query.

    Like ``safe_repo_context``, but a missing directory or a non-repository
    raises ``ValueError`` instead of a GitPython exception.

    Raises:
        ValueError: If ``project_dir`` is not a git repository.
    """
    try:
        with safe_repo_context(project_dir) as repo:
            yield repo
    except (InvalidGitRepositoryError, NoSuchPathError):
        raise ValueError(f"Not a git repository: {project_dir}") from None


def _normalize_git_path(path: Path, base_dir: Path) -> str:
    """Convert a path to git-compatible format.

    Args:
        path: Path to normalize
        base_dir: Base directory to make path relative to

    Returns:
        Git-compatible path string using forward slashes
    """
    relative_path = path.relative_to(base_dir)
    return str(relative_path).replace("\\", "/")
