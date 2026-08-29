"""Directory utilities for file operations.

This module provides functions for file discovery and listing with gitignore support.
We use the external igittigitt library for handling .gitignore patterns.
"""

import logging
import os
from pathlib import Path
from typing import Callable, List, Optional, Union

from igittigitt import IgnoreParser

from mcp_workspace.file_tools.path_utils import normalize_path

logger = logging.getLogger(__name__)


def is_path_in_git_dir(path: str) -> bool:
    """Check if a path is inside a .git directory.

    Returns:
        True if any component of the path is ".git".
    """
    return ".git" in Path(path).parts


def is_path_gitignored(path: str, project_dir: Path) -> bool:
    """Check if a path is gitignored.

    Checks both whether the path is inside a .git directory and whether it
    matches any pattern in the root .gitignore file.

    Works on non-existent paths (e.g., blocking save_file to a new *.log path).

    Args:
        path: Relative path to check (relative to project_dir).
        project_dir: Project root directory containing .gitignore.

    Returns:
        True if the path should be considered ignored.
    """
    if is_path_in_git_dir(path):
        return True

    gitignore_path = project_dir / ".gitignore"
    matcher = read_gitignore_rules(gitignore_path)
    if matcher is None:
        return False

    abs_path = str(project_dir / path)
    return bool(matcher(abs_path))


def _discover_files(directory: Path, project_dir: Path) -> List[str]:
    """Discover all files recursively, excluding the .git directory.

    Returns:
        List of file paths relative to project_dir.
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
            rel_file_path = str(rel_root / file)
            discovered_files.append(rel_file_path)

    return discovered_files


def read_gitignore_rules(
    gitignore_path: Path,
) -> Optional[Callable[[str], bool]]:
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


def apply_gitignore_filter(
    file_paths: List[str], matcher: Optional[Callable[[str], bool]], project_dir: Path
) -> List[str]:
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
        if not matcher(abs_file_path):
            filtered_files.append(file_path)

    logger.info(
        "Applied gitignore filtering: %s files found, %s after filtering",
        len(file_paths),
        len(filtered_files),
    )
    return filtered_files


def filter_with_gitignore(
    file_paths: List[str], base_dir: Path, project_dir: Path
) -> List[str]:
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
    directory: Union[str, Path], project_dir: Path, use_gitignore: bool = True
) -> List[str]:
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
