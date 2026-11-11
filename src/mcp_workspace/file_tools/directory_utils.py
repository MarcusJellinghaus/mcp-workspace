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


def _info_exclude_path(project_dir: Path) -> Path | None:
    """Locate the ``info/exclude`` file of the repository at project_dir.

    A ``.git`` file (worktree or submodule) points to the git directory with a
    ``gitdir:`` line; a worktree's git directory names the shared one in
    ``commondir``.

    Returns:
        The path of the ``info/exclude`` file to read (it need not exist), or
        None if the ``.git`` file cannot be read or has no ``gitdir:`` line.
    """
    git = project_dir / ".git"
    if git.is_file():
        try:
            lines = git.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            logger.warning("Error reading %s: %s", git, e)
            return None
        gitdirs = [line for line in lines if line.startswith("gitdir:")]
        if not gitdirs:
            return None
        # An absolute gitdir stays absolute when joined
        git = project_dir / gitdirs[0].removeprefix("gitdir:").strip()

    commondir = git / "commondir"
    if commondir.is_file():
        try:
            git = git / commondir.read_text(encoding="utf-8").strip()
        except OSError as e:
            logger.warning("Error reading %s: %s", commondir, e)
            return None
    return git / "info" / "exclude"


def _load_rule_file(parser: IgnoreParser, rule_file: Path, base_dir: Path) -> None:
    """Append the rules of one rule file to parser, if the file exists.

    Args:
        parser: Parser to extend.
        rule_file: The .gitignore or info/exclude file to read.
        base_dir: Directory the file's patterns are relative to.
    """
    if not rule_file.is_file():
        logger.debug("No rule file at %s", rule_file)
        return
    try:
        parser.parse_rule_file(rule_file, base_dir=base_dir)
    except Exception as e:
        logger.warning("Error reading rule file %s: %s", rule_file, e)
        return
    logger.debug("Loaded %s (%s rules)", rule_file, len(parser.rules))


def _rules_for(directory: Path, project_dir: Path) -> IgnoreParser:
    """Build the rules in effect for the entries of a directory.

    Rules are loaded in git's precedence order, lowest first: info/exclude,
    the root .gitignore, then each .gitignore down to directory. The last
    matching rule wins. A .gitignore inside an ignored directory is not read.

    Args:
        directory: Absolute directory at or below project_dir.
        project_dir: Project root directory.

    Returns:
        A parser holding the rules in precedence order.
    """
    parser = IgnoreParser()
    exclude = _info_exclude_path(project_dir)
    if exclude is not None:
        _load_rule_file(parser, exclude, project_dir)
    _load_rule_file(parser, project_dir / ".gitignore", project_dir)

    current = project_dir
    for part in directory.relative_to(project_dir).parts:
        current /= part
        # Git never descends into an ignored directory
        if parser.match(current):
            break
        _load_rule_file(parser, current / ".gitignore", current)
    return parser


def _matches_rules(path: str, project_dir: Path) -> bool:
    """Check one spelling of a path against the rules of its ancestor chain.

    Returns:
        True if the rules ignore the path; False for the project root and for
        a path that leaves project_dir.
    """
    base = Path(os.path.normpath(project_dir))
    full = Path(os.path.normpath(base / path))
    if full == base or not full.is_relative_to(base):
        return False
    return _rules_for(full.parent, base).match(full)


def is_path_gitignored(path: str, project_dir: Path) -> bool:
    """Check if a path is gitignored.

    Checks both whether the path is inside a .git directory and whether git's
    rules ignore it: .git/info/exclude, the root .gitignore and every deeper
    .gitignore on the way to the path. The rules are tried on the path as
    spelled, on its canonical spelling, and on the location it resolves to, so
    a link into an ignored location counts as ignored.

    Works on non-existent paths (e.g., blocking save_file to a new *.log path).

    Args:
        path: Relative path to check (relative to project_dir).
        project_dir: Project root directory.

    Returns:
        True if the path should be considered ignored.
    """
    if is_path_in_git_dir(path):
        return True

    joined = project_dir / path
    if resolves_into_git_dir(joined, project_dir):
        return True

    candidates = {
        path,
        canonical_spelling(path),
        _resolved_relative(joined, project_dir),
    }
    return any(
        _matches_rules(candidate, project_dir)
        for candidate in candidates
        if candidate is not None
    )


def check_path_not_gitignored(file_path: str, project_dir: Path) -> None:
    """Raise ValueError if a path is excluded by gitignore rules or inside .git.

    An absolute path is checked relative to project_dir. One that is not below
    project_dir is left for ``normalize_path`` to refuse.

    Args:
        file_path: Path to check, relative to project_dir or absolute.
        project_dir: Project root directory.

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
            f"Path '{file_path}' is excluded by .gitignore rules and cannot be "
            "accessed. Use list_directory() to see available files."
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
