"""Directory utilities for file operations.

This module provides functions for file discovery and listing with gitignore support.
We use the external igittigitt library for handling .gitignore patterns.
"""

import logging
import os
from collections.abc import Callable
from pathlib import Path

from igittigitt import IgnoreParser

from mcp_workspace.file_tools.path_utils import normalize_path, resolves_into_git_dir
from mcp_workspace.utils.git_paths import canonical_spelling, is_path_in_git_dir

logger = logging.getLogger(__name__)


def _resolved_relative(path: Path, project_dir: Path) -> str | None:
    """Return where a path really points, relative to the project directory.

    Returns:
        The resolved project-relative path, or None if it resolves outside the
        project or cannot be resolved.
    """
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def is_path_gitignored(path: str, project_dir: Path) -> bool:
    """Check if a path is gitignored.

    Checks both whether the path is inside a .git directory and whether it
    matches any pattern in the root .gitignore file. The patterns are tried on
    the path as spelled, on its canonical spelling, and on the location it
    resolves to, so a link into an ignored location counts as ignored.

    Works on non-existent paths (e.g., blocking save_file to a new *.log path).

    Args:
        path: Relative path to check (relative to project_dir).
        project_dir: Project root directory containing .gitignore.

    Returns:
        True if the path should be considered ignored.
    """
    if is_path_in_git_dir(path):
        return True

    joined = project_dir / path
    if resolves_into_git_dir(joined, project_dir):
        return True

    gitignore_path = project_dir / ".gitignore"
    matcher = read_gitignore_rules(gitignore_path)
    if matcher is None:
        return False

    candidates = {
        path,
        canonical_spelling(path),
        _resolved_relative(joined, project_dir),
    }
    return any(
        matcher(str(project_dir / candidate))
        for candidate in candidates
        if candidate is not None
    )


def check_path_not_gitignored(file_path: str, project_dir: Path) -> None:
    """Raise ValueError if a path is excluded by .gitignore or inside .git.

    An absolute path is checked relative to project_dir. One that is not below
    project_dir is left for ``normalize_path`` to refuse.

    Args:
        file_path: Path to check, relative to project_dir or absolute.
        project_dir: Project root directory containing .gitignore.

    Raises:
        ValueError: If the path is excluded.
    """
    path = Path(file_path)
    if path.is_absolute():
        try:
            file_path = path.relative_to(project_dir).as_posix()
        except ValueError:
            return
    if is_path_gitignored(file_path, project_dir):
        raise ValueError(
            f"File '{file_path}' is excluded by .gitignore and cannot be accessed. "
            "Use list_directory() to see available files."
        )


def _discover_files(directory: Path, project_dir: Path) -> list[str]:
    """Discover all files recursively, excluding the .git directory.

    Returns:
        List of file paths relative to project_dir, forward-slash separated
        on every platform; this is the enforcement point for all listing and
        search tools.
    """
    discovered_files = []

    for root, dirs, files in os.walk(directory):
        # Skip .git directories
        dirs[:] = [d for d in dirs if not is_path_in_git_dir(d)]

        root_path = Path(root)
        try:
            rel_root = root_path.relative_to(project_dir)
        except ValueError:
            continue

        for file in files:
            # A .git file marks a worktree or submodule
            if is_path_in_git_dir(file):
                continue
            rel_file_path = rel_root.joinpath(file).as_posix()
            discovered_files.append(rel_file_path)

    return discovered_files


def read_gitignore_rules(
    gitignore_path: Path,
) -> Callable[[str], bool] | None:
    """Read and parse a .gitignore file to create a matcher function.

    Args:
        gitignore_path: Path to the .gitignore file

    Returns:
        A matcher function, or None if the file doesn't exist or cannot be parsed
    """
    if not gitignore_path.is_file():
        logger.debug("No .gitignore file found at %s", gitignore_path)
        return None

    try:
        parser = IgnoreParser()
        parser.parse_rule_file(gitignore_path)
        logger.debug(
            "Loaded .gitignore at %s (%s rules)", gitignore_path, len(parser.rules)
        )

        def matcher(path: str) -> bool:
            return bool(parser.match(path))

        return matcher

    except Exception as e:
        logger.warning("Error reading/parsing gitignore: %s", str(e))
        return None


def _link_target_ignored(
    path: Path, matcher: Callable[[str], bool], project_dir: Path
) -> bool:
    """Check whether a path is a symlink to a location the matcher ignores.

    Returns:
        True for a symlink whose target inside the project is ignored.
    """
    if not path.is_symlink():
        return False
    target = _resolved_relative(path, project_dir)
    return target is not None and bool(matcher(str(project_dir / target)))


def apply_gitignore_filter(
    file_paths: list[str], matcher: Callable[[str], bool] | None, project_dir: Path
) -> list[str]:
    """Filter a list of file paths using a gitignore matcher function.

    Args:
        file_paths: List of file paths to filter
        matcher: Function that takes a path and returns True if it should be ignored
        project_dir: Base directory for resolving relative paths to absolute

    Returns:
        Filtered list of file paths that are not ignored

    Raises:
        ValueError: If project_dir is None
    """
    if matcher is None:
        return file_paths

    filtered_files = []

    # Validate project_dir parameter
    if project_dir is None:
        raise ValueError("Project directory cannot be None")

    for file_path in file_paths:
        # Convert to absolute path for the matcher
        abs_file_path = str(project_dir / file_path)

        # The matcher returns True if the file should be ignored
        if not matcher(abs_file_path) and not _link_target_ignored(
            project_dir / file_path, matcher, project_dir
        ):
            filtered_files.append(file_path)

    logger.info(
        "Applied gitignore filtering: %s files found, %s after filtering",
        len(file_paths),
        len(filtered_files),
    )
    return filtered_files


def filter_with_gitignore(
    file_paths: list[str], base_dir: Path, project_dir: Path
) -> list[str]:
    """Filter a list of file paths using .gitignore rules.

    Args:
        file_paths: List of file paths to filter
        base_dir: Directory containing the .gitignore file
        project_dir: Project directory path

    Returns:
        List of file paths that are not ignored
    """
    gitignore_path = base_dir / ".gitignore"

    # Get the matcher function from the gitignore file
    matcher = read_gitignore_rules(gitignore_path)

    if matcher is None:
        return file_paths

    # Use the matcher for more complex gitignore patterns
    return apply_gitignore_filter(file_paths, matcher, project_dir)


def list_files(
    directory: str | Path, project_dir: Path, use_gitignore: bool = True
) -> list[str]:
    """List all files in a directory and its subdirectories with optional gitignore filtering.

    Args:
        directory: Directory to list files from
        project_dir: Project directory path
        use_gitignore: Whether to apply gitignore filtering

    Returns:
        List of file paths

    Raises:
        ValueError: If project_dir is None
        FileNotFoundError: If the directory does not exist
        NotADirectoryError: If the path is not a directory
    """
    # Validate project_dir parameter
    if project_dir is None:
        raise ValueError("Project directory cannot be None")

    abs_path, rel_path = normalize_path(str(directory), project_dir)

    if not abs_path.exists():
        raise FileNotFoundError(f"Directory '{directory}' does not exist")

    if not abs_path.is_dir():
        raise NotADirectoryError(f"Path '{directory}' is not a directory")

    try:
        all_files = _discover_files(abs_path, project_dir)
        logger.info("Discovered %s files in %s", len(all_files), rel_path)

        if not use_gitignore:
            return all_files

        # Apply gitignore filtering
        return filter_with_gitignore(all_files, abs_path, project_dir)

    except Exception as e:
        logger.error("Error listing files in directory %s: %s", rel_path, str(e))
        raise
