"""Git staging operations for managing staged changes."""

from pathlib import Path
from typing import Callable

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from .core import (
    GitResult,
    _chunk_paths,
    _normalize_git_path,
    logger,
    run_git_raw,
    safe_repo_context,
    to_git_paths,
)
from .repository_status import is_git_repository


def stage_specific_files(files: list[Path], project_dir: Path) -> bool:
    """Stage specific files for commit.

    Args:
        files: List of file paths to stage
        project_dir: Path to the project directory containing the git repository

    Returns:
        True if all specified files were staged successfully, False otherwise

    Note:
        - Handles both absolute and relative file paths
        - Validates files exist and are within project directory; validation
          failures (missing file, outside project) return False before anything
          is staged
        - Logs appropriate warnings/errors for failed operations
        - Staging is no longer all-or-nothing: once validation passes, files are
          staged git-add-chunk by git-add-chunk, so a chunk can partially stage
          valid paths and fail only on an ignored one, and a failure in a later
          chunk leaves earlier chunks staged
        - Staging is idempotent, so retrying after a False return is safe
        - Directories are accepted and staged recursively by git
    """
    logger.debug("Staging %d specific files in %s", len(files), project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    # Handle empty list - this is a valid no-op case
    if not files:
        logger.debug("No files to stage - success")
        return True

    try:
        with safe_repo_context(project_dir) as repo:
            # Validate and convert all file paths first
            relative_paths = []
            for file_path in files:
                # Check if file exists
                if not file_path.exists():
                    logger.error("File does not exist: %s", file_path)
                    return False

                # Get git-compatible path
                try:
                    git_path = _normalize_git_path(file_path, project_dir)
                    relative_paths.append(git_path)
                except ValueError:
                    logger.error(
                        "File %s is outside project directory %s",
                        file_path,
                        project_dir,
                    )
                    return False

            logger.debug("Staging files: %s", relative_paths)
            for chunk in _chunk_paths(relative_paths):
                with repo.git.custom_environment(GIT_LITERAL_PATHSPECS="1"):
                    # Stage through real git so clean filters and .gitattributes
                    # apply - do not use repo.index.add.
                    repo.git.add("--", *chunk)

            logger.debug(
                "Successfully staged %d files: %s", len(relative_paths), relative_paths
            )
            return True

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.error("Git error staging files: %s", e)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.error("Unexpected error staging files: %s", e)
        return False


_ChunkArgs = Callable[[list[str]], tuple[str, tuple[str, ...]]]


def _run_chunked(
    paths: list[Path],
    project_dir: Path,
    func_name: str,
    make_chunk_args: Callable[[Repo], _ChunkArgs],
) -> GitResult:
    """Run one literal-pathspec git command per chunk of ``paths``.

    Args:
        paths: Absolute paths, or paths relative to ``project_dir``
        project_dir: Path to the project directory containing the git repository
        func_name: Public function name, used in log messages
        make_chunk_args: Called once with the open repo (after path validation);
            returns a builder mapping a chunk to ``(label, git_args)``, where
            ``label`` names the command in the ``git <label> failed`` error.

    Returns:
        GitResult as documented on the public callers.
    """
    try:
        with safe_repo_context(project_dir) as repo:
            if not paths:
                return {
                    "success": True,
                    "error": None,
                    "returncode": None,
                    "stderr": None,
                }
            try:
                rel_paths = to_git_paths(paths, project_dir)
            except ValueError as e:
                logger.debug("%s failed: %s", func_name, e)
                return {
                    "success": False,
                    "error": str(e),
                    "returncode": None,
                    "stderr": None,
                }

            chunk_args = make_chunk_args(repo)
            returncode, stderr = 0, ""
            for chunk in _chunk_paths(rel_paths):
                label, args = chunk_args(chunk)
                returncode, _, stderr = run_git_raw(repo, *args, literal_paths=True)
                if returncode != 0:
                    logger.debug(
                        "git %s failed (exit %s): %s", label, returncode, stderr
                    )
                    return {
                        "success": False,
                        "error": f"git {label} failed (exit {returncode})",
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


def unstage_paths(paths: list[Path], project_dir: Path) -> GitResult:
    """Remove ``paths`` from the index, keeping their working-tree content.

    Works on an unborn HEAD (the paths become untracked). Idempotent: paths
    that are not staged are a success. Paths are matched literally (``*``,
    ``[`` and ``:(`` have no special meaning) and long lists are split into
    several git calls to stay under the Windows command-line limit.

    Args:
        paths: Absolute paths, or paths relative to ``project_dir``
        project_dir: Path to the project directory containing the git repository

    Returns:
        GitResult; ``success`` is True when every path is unstaged. An empty
        ``paths`` is a success without running git. A non-repository or a path
        outside ``project_dir`` is an error result with ``returncode`` and
        ``stderr`` None. A failing chunk leaves earlier chunks unstaged.
    """
    logger.debug("Unstaging paths %s in %s", paths, project_dir)

    def make_chunk_args(repo: Repo) -> _ChunkArgs:
        head_rc, _, _ = run_git_raw(repo, "rev_parse", "--verify", "-q", "HEAD")

        def chunk_args(chunk: list[str]) -> tuple[str, tuple[str, ...]]:
            if head_rc == 0:
                return "reset", ("reset", "-q", "HEAD", "--", *chunk)
            rm_args = ("rm", "--cached", "-r", "-q", "--ignore-unmatch", "--")
            return "rm", (*rm_args, *chunk)

        return chunk_args

    return _run_chunked(paths, project_dir, "unstage_paths", make_chunk_args)


def renormalize_paths(paths: list[Path], project_dir: Path) -> GitResult:
    """Re-stage ``paths`` through ``git add --renormalize``.

    Applies the current ``.gitattributes`` line-ending rules to the index, so
    a file whose only change is line endings stops showing as modified.
    ``--renormalize`` implies ``-u``: files with real edits are staged too,
    which is what lets a caller detect them. Undo with ``unstage_paths``.
    Paths are matched literally and long lists are split into several git
    calls to stay under the Windows command-line limit.

    There is no existence pre-check. A deleted tracked path or a path that
    never existed makes git exit 128, and nothing in that chunk is staged.
    An untracked path or stat-only dirt is a success that stages nothing.

    Args:
        paths: Absolute paths, or paths relative to ``project_dir``
        project_dir: Path to the project directory containing the git repository

    Returns:
        GitResult; ``success`` is True when every chunk succeeds. An empty
        ``paths`` is a success without running git. A non-repository or a path
        outside ``project_dir`` is an error result with ``returncode`` and
        ``stderr`` None. A failing chunk leaves earlier chunks staged.
    """
    logger.debug("Renormalizing paths %s in %s", paths, project_dir)

    def chunk_args(chunk: list[str]) -> tuple[str, tuple[str, ...]]:
        return "add --renormalize", ("add", "--renormalize", "--", *chunk)

    return _run_chunked(paths, project_dir, "renormalize_paths", lambda _: chunk_args)


def stage_all_changes(project_dir: Path) -> bool:
    """Stage all unstaged changes (both modified and untracked files) for commit.

    Args:
        project_dir: Path to the project directory containing the git repository

    Returns:
        True if all unstaged changes were staged successfully, False otherwise

    Note:
        - Stages both modified tracked files (including deletions) and untracked files
        - Returns True on a clean tree (`git add --all` is a no-op)
        - Uses git add --all to handle deletions properly
        - Returns False if staging operation fails
    """
    logger.debug("Staging all changes in %s", project_dir)

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return False

    try:
        with safe_repo_context(project_dir) as repo:
            # Use git add --all to stage all changes (additions, modifications, deletions)
            repo.git.add("--all")

        logger.debug("Staged all changes")
        return True

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.error("Git error staging all changes: %s", e)
        return False
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.error("Unexpected error staging all changes: %s", e)
        return False
