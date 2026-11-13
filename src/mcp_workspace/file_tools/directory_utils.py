"""Directory utilities for file operations.

This module provides functions for file discovery and listing with gitignore support.
We use the external igittigitt library for handling .gitignore patterns.
"""

import logging
import os
import sys
from collections.abc import Callable
from enum import IntEnum
from pathlib import Path

from igittigitt import IgnoreParser

from mcp_workspace.file_tools.access_rules import (
    ACCESS_RULES_FILE,
    READ_ONLY,
    AccessRules,
    load_access_rules,
)
from mcp_workspace.file_tools.access_rules import (
    validate_access_rules as validate_access_rules,
)
from mcp_workspace.file_tools.path_utils import normalize_path, resolves_into_git_dir
from mcp_workspace.utils.git_paths import canonical_spelling, is_path_in_git_dir

logger = logging.getLogger(__name__)


class FileAccess(IntEnum):
    """Effective access to a path; a higher value grants more."""

    HIDDEN = 0
    READ_ONLY = 1
    READ_WRITE = 2


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
        except (OSError, UnicodeDecodeError) as e:
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
        except (OSError, UnicodeDecodeError) as e:
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

    if resolves_into_git_dir(project_dir / path, project_dir):
        return True

    return any(
        _matches_rules(spelling, project_dir)
        for spelling in _spellings(path, project_dir)
    )


def _spellings(path: str, project_dir: Path) -> set[str]:
    """Return the spellings of a path that rules are checked against.

    Args:
        path: Relative path (relative to project_dir).
        project_dir: Project root directory.

    Returns:
        The path as spelled, its canonical spelling, and the location it
        resolves to when that is inside the project.
    """
    spellings = {path, canonical_spelling(path)}
    resolved = _resolved_relative(project_dir / path, project_dir)
    if resolved is not None:
        spellings.add(resolved)
    return spellings


def _is_rules_file(rel_path: str) -> bool:
    """Tell whether a project-relative path names the root rules file.

    Returns:
        True if the path is ``.mcp-file-access`` at the project root.
    """
    # Windows matches names case-insensitively; the file name is lower case
    folded = rel_path.casefold() if sys.platform == "win32" else rel_path
    return folded == ACCESS_RULES_FILE


def _access_of_spelling(
    rel_path: str, project_dir: Path, rules: AccessRules
) -> tuple[FileAccess, str]:
    """Decide the access of one spelling of a path, ignoring ``.git``.

    Returns:
        The access level and the reason it differs from the default.
    """
    ignored = _matches_rules(rel_path, project_dir)
    rule = rules.match(rel_path, is_dir=(project_dir / rel_path).is_dir())
    if rule is not None:
        base = (
            FileAccess.READ_ONLY if rule.level == READ_ONLY else FileAccess.READ_WRITE
        )
    else:
        base = FileAccess.HIDDEN if ignored else FileAccess.READ_WRITE

    if _is_rules_file(rel_path):
        return min(base, FileAccess.READ_ONLY), "built-in"
    if rules.problems:
        access = FileAccess.HIDDEN if ignored else FileAccess.READ_ONLY
        return access, f"{ACCESS_RULES_FILE} is invalid: " + "; ".join(rules.problems)
    if rule is not None:
        return base, f"rule '{rule.pattern}' in {ACCESS_RULES_FILE}"
    return base, ""


def _access(path: str, project_dir: Path, rules: AccessRules) -> tuple[FileAccess, str]:
    """Decide the effective access to a path: gitignore default plus rules.

    ``.git`` is always hidden. Otherwise the last matching rule overrides the
    gitignore default, the rules file is capped at read-only, and an invalid
    rules file leaves committed paths read-only and ignored paths hidden. The
    most restrictive result across the path's spellings wins.

    Args:
        path: Relative path (relative to project_dir).
        project_dir: Project root directory.
        rules: The project's rules, loaded once per tool call.

    Returns:
        The access level and its reason: empty for the default, else the
        rule, ``built-in`` or the invalid rules file's problems.
    """
    if is_path_in_git_dir(path) or resolves_into_git_dir(
        project_dir / path, project_dir
    ):
        return FileAccess.HIDDEN, ""
    # Sorted, so ties between spellings always give the same reason
    return min(
        (
            _access_of_spelling(spelling, project_dir, rules)
            for spelling in sorted(_spellings(path, project_dir))
        ),
        key=lambda result: result[0],
    )


def get_file_access(path: str, project_dir: Path) -> FileAccess:
    """Return the effective access to a path.

    Args:
        path: Relative path (relative to project_dir).
        project_dir: Project root directory.

    Returns:
        The path's access level under .gitignore and ``.mcp-file-access``.
    """
    return _access(path, project_dir, load_access_rules(project_dir))[0]


def _excluded_error(file_path: str) -> ValueError:
    """Build the refusal for a path hidden by gitignore rules.

    Returns:
        The error to raise, naming file_path.
    """
    return ValueError(
        f"Path '{file_path}' is excluded by .gitignore rules and cannot be "
        "accessed. Use list_directory() to see available files."
    )


def require_access(file_path: str, project_dir: Path, needed: FileAccess) -> None:
    """Raise ValueError unless a path grants the needed access.

    An absolute path is checked relative to project_dir. One that is not below
    project_dir is left for ``normalize_path`` to refuse.

    Args:
        file_path: Path to check, relative to project_dir or absolute.
        project_dir: Project root directory.
        needed: ``READ_ONLY`` to read, ``READ_WRITE`` to write.

    Raises:
        ValueError: If the path is hidden, or read-only and a write is needed.
    """  # noqa: DOC501 - _excluded_error returns the documented ValueError
    path = Path(file_path)
    if path.is_absolute():
        try:
            file_path = path.relative_to(project_dir).as_posix()
        except ValueError:
            return
    access, reason = _access(file_path, project_dir, load_access_rules(project_dir))
    if access is FileAccess.HIDDEN:
        raise _excluded_error(file_path)
    if needed is FileAccess.READ_WRITE and access is FileAccess.READ_ONLY:
        raise ValueError(f"No write access to '{file_path}' ({reason})")


def check_path_not_gitignored(file_path: str, project_dir: Path) -> None:
    """Raise ValueError if a path is excluded by gitignore rules or inside .git.

    An absolute path is checked relative to project_dir. One that is not below
    project_dir is left for ``normalize_path`` to refuse.

    Args:
        file_path: Path to check, relative to project_dir or absolute.
        project_dir: Project root directory.

    Raises:
        ValueError: If the path is excluded.
    """  # noqa: DOC501, DOC502 - _excluded_error returns the documented ValueError
    path = Path(file_path)
    if path.is_absolute():
        try:
            file_path = path.relative_to(project_dir).as_posix()
        except ValueError:
            return
    if is_path_gitignored(file_path, project_dir):
        raise _excluded_error(file_path)


def _discover_files(
    directory: Path, project_dir: Path, skip: Callable[[Path], bool] | None = None
) -> list[str]:
    """Discover all files recursively, excluding the .git directory.

    Args:
        directory: Absolute directory to walk.
        project_dir: Project root directory.
        skip: Optional predicate called with the absolute path of every
            subdirectory and file; a skipped directory is never entered and a
            skipped file is not returned.

    Returns:
        List of file paths relative to project_dir, forward-slash separated
        on every platform; this is the enforcement point for all listing and
        search tools.
    """
    discovered_files = []

    for root, dirs, files in os.walk(directory):
        root_path = Path(root)

        # Skip .git directories
        dirs[:] = [
            d
            for d in dirs
            if not is_path_in_git_dir(d) and not (skip and skip(root_path / d))
        ]

        try:
            rel_root = root_path.relative_to(project_dir)
        except ValueError:
            continue

        for file in files:
            # A .git file marks a worktree or submodule
            if is_path_in_git_dir(file):
                continue
            if skip and skip(root_path / file):
                continue
            rel_file_path = rel_root.joinpath(file).as_posix()
            discovered_files.append(rel_file_path)

    return discovered_files


def _gitignore_skip(start: Path, project_dir: Path) -> Callable[[Path], bool]:
    """Build a skip predicate for a top-down walk from start.

    Each directory's rules are its parent's rules plus its own .gitignore. A
    directory without a .gitignore shares its parent's parser; one with a
    .gitignore gets a copy, so siblings never share rules.

    Args:
        start: Absolute directory the walk starts at, not itself ignored.
        project_dir: Project root directory.

    Returns:
        A predicate that is True for an entry the rules ignore, or for a
        symlink that points into an ignored location.
    """
    parsers = {start: _rules_for(start, project_dir)}

    def parser_for(directory: Path) -> IgnoreParser:
        # The walk is top-down, so the parent is already known
        if directory not in parsers:
            parent = parser_for(directory.parent)
            parsers[directory] = parent
            gitignore = directory / ".gitignore"
            if gitignore.is_file():
                parser = IgnoreParser()
                parser.rules = list(parent.rules)
                _load_rule_file(parser, gitignore, directory)
                parsers[directory] = parser
        return parsers[directory]

    def skip(path: Path) -> bool:
        if parser_for(path.parent).match(path):
            return True
        return path.is_symlink() and is_path_gitignored(
            path.relative_to(project_dir).as_posix(), project_dir
        )

    return skip


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
        if not use_gitignore:
            files = _discover_files(abs_path, project_dir)
        elif is_path_gitignored(rel_path, project_dir):
            files = []
        else:
            files = _discover_files(
                abs_path, project_dir, _gitignore_skip(abs_path, project_dir)
            )
        logger.debug("Discovered %s files in %s", len(files), rel_path)
        return files

    except Exception as e:
        logger.error("Error listing files in directory %s: %s", rel_path, str(e))
        raise
