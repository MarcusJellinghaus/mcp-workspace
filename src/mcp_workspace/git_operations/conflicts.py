"""Conflict inspection and resolution for a stopped rebase or merge."""

from pathlib import Path

from git.exc import GitCommandError

from .core import logger, open_repo_for_query, run_git_raw
from .porcelain_parsers import parse_ls_files_u_z


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
