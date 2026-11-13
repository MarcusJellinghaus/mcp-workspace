"""Effective file access: the gitignore default plus ``.mcp-file-access`` rules.

This module decides what a path grants, checks whole trees before a move or
delete, and lists the files the rules expose. The gitignore-only layer it
builds on lives in ``directory_utils``.
"""

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from mcp_workspace.file_tools.access_rules import (
    ACCESS_RULES_FILE,
    READ_ONLY,
    AccessRules,
    load_access_rules,
)
from mcp_workspace.file_tools.access_rules import (
    validate_access_rules as validate_access_rules,
)
from mcp_workspace.file_tools.directory_utils import (
    _discover_files,
    _excluded_error,
    _gitignore_skip,
    _matches_rules,
    _resolved_relative,
    _spellings,
    is_path_gitignored,
)
from mcp_workspace.file_tools.path_utils import normalize_path, resolves_into_git_dir
from mcp_workspace.utils.git_paths import canonical_spelling, is_path_in_git_dir

logger = logging.getLogger(__name__)

_BUILT_IN = "built-in"


class FileAccess(IntEnum):
    """Effective access to a path; a higher value grants more."""

    HIDDEN = 0
    READ_ONLY = 1
    READ_WRITE = 2


def _is_rules_file(rel_path: str) -> bool:
    """Tell whether a project-relative path names the root rules file.

    Returns:
        True if the path is ``.mcp-file-access`` at the project root.
    """
    # Windows matches names case-insensitively; the file name is lower case
    folded = rel_path.casefold() if sys.platform == "win32" else rel_path
    return folded == ACCESS_RULES_FILE


def _rule_of_spelling(
    rel_path: str, rules: AccessRules, is_dir: bool
) -> tuple[FileAccess | None, str]:
    """Decide what the rules file and the built-in rule say about one spelling.

    Returns:
        ``(READ_ONLY, "built-in")`` for the rules file, the level and reason
        of the last matching rule, or ``(None, "")`` when no rule matches.
    """
    if _is_rules_file(rel_path):
        return FileAccess.READ_ONLY, _BUILT_IN
    rule = rules.match(rel_path, is_dir=is_dir)
    if rule is None:
        return None, ""
    level = FileAccess.READ_ONLY if rule.level == READ_ONLY else FileAccess.READ_WRITE
    return level, f"rule '{rule.pattern}' in {ACCESS_RULES_FILE}"


def _rule_access(
    rel: str, rules: AccessRules, is_dir: bool = False
) -> tuple[FileAccess | None, str]:
    """Decide what the rules give a path, without consulting gitignore.

    The path is checked as given and in its canonical spelling; the most
    restrictive match wins.

    Args:
        rel: Project-relative path with forward slashes.
        rules: The project's rules, loaded once per tool call.
        is_dir: Whether the path is a directory.

    Returns:
        The access level and its reason, or ``(None, "")`` when neither a
        rule nor the built-in rule applies.
    """
    matches: list[tuple[FileAccess, str]] = []
    # Sorted, so ties between spellings always give the same reason
    for spelling in sorted({rel, canonical_spelling(rel)}):
        level, reason = _rule_of_spelling(spelling, rules, is_dir)
        if level is not None:
            matches.append((level, reason))
    if not matches:
        return None, ""
    return min(matches, key=lambda match: match[0])


def _access_of_spelling(
    rel_path: str, project_dir: Path, rules: AccessRules
) -> tuple[FileAccess, str]:
    """Decide the access of one spelling of a path, ignoring ``.git``.

    Returns:
        The access level and the reason it differs from the default.
    """
    ignored = _matches_rules(rel_path, project_dir)
    # Like igittigitt, which _matches_rules uses: a missing path is a directory
    is_dir = not (project_dir / rel_path).is_file()
    level, reason = _rule_of_spelling(rel_path, rules, is_dir)

    if reason == _BUILT_IN:
        # Capped at read-only; ignored and matched by no rule, it stays hidden
        hidden = ignored and rules.match(rel_path, is_dir=is_dir) is None
        return (FileAccess.HIDDEN if hidden else FileAccess.READ_ONLY), reason
    if rules.problems:
        access = FileAccess.HIDDEN if ignored else FileAccess.READ_ONLY
        return access, f"{ACCESS_RULES_FILE} is invalid: " + "; ".join(rules.problems)
    if level is None:
        return (FileAccess.HIDDEN if ignored else FileAccess.READ_WRITE), ""
    return level, reason


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


def _tree_entries(src_abs: Path) -> list[Path]:
    """Return what a move or delete of src_abs carries along.

    Returns:
        src_abs itself for a file or a link; else every non-directory entry
        below it, links included, also inside ignored subdirectories.
    """
    if src_abs.is_symlink() or not src_abs.is_dir():
        return [src_abs]
    return [p for p in src_abs.rglob("*") if p.is_symlink() or not p.is_dir()]


def _below_link(path: Path, top: Path) -> bool:
    """Tell whether path, or an ancestor of it up to top, is a symlink.

    Returns:
        True if a link lies on the way from top to path, both included.
    """
    return any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(top))


def _tree_member(root: tuple[Path, str], suffix: str) -> tuple[Path, str]:
    """Return a tree entry's absolute and project-relative path.

    Args:
        root: The tree's absolute and project-relative path.
        suffix: The entry relative to the tree, ``.`` for the root itself.

    Returns:
        The entry's paths, spelled like root.
    """
    if suffix == ".":
        return root
    return root[0] / suffix, f"{root[1]}/{suffix}"


def _through_linked_ancestors(rel: str, project_dir: Path) -> str | None:
    """Return a path with its ancestors resolved, the entry itself kept.

    Moving or deleting a link leaves its target alone, so only the
    directories above the entry are followed.

    Returns:
        The project-relative path through resolved ancestors, or None when it
        is the path as given or the ancestors resolve outside the project.
    """
    parent, _, name = rel.rpartition("/")
    if not parent:
        return None
    resolved = _resolved_relative(project_dir / parent, project_dir)
    if resolved is None or resolved == parent:
        return None
    return name if resolved == "." else f"{resolved}/{name}"


def _check_not_read_only(rel: str, project_dir: Path, rules: AccessRules) -> None:
    """Raise ValueError if a path is read-only by rule.

    The path is checked as given, canonically and through linked ancestors;
    any read-only spelling refuses it.

    Raises:
        ValueError: If a rule or the built-in rule makes rel read-only.
    """
    spellings = [rel]
    resolved = _through_linked_ancestors(rel, project_dir)
    if resolved is not None:
        spellings.append(resolved)
    for spelling in spellings:
        level, reason = _rule_access(spelling, rules)
        if level is FileAccess.READ_ONLY:
            raise ValueError(f"No write access to '{rel}' ({reason})")


def _check_no_exposure(
    src: tuple[Path, str],
    dest: tuple[Path, str],
    suffixes: list[str],
    project_dir: Path,
    rules: AccessRules,
) -> None:
    """Raise ValueError if a move would make a hidden file accessible.

    Gitignore is consulted only for the files the source walk reports as
    ignored. The destination is judged by the rules in effect before the move.

    Args:
        src: Absolute and project-relative path of the moved tree.
        dest: Absolute and project-relative path it moves to.
        suffixes: The tree's entries relative to it, ``.`` for a single file.
        project_dir: Project root directory.
        rules: The project's rules, loaded once per tool call.

    Raises:
        ValueError: If a file hidden at its source is not hidden at its
            destination; the message names no file.
    """
    # Built once per call; each loads a directory's .gitignore chain once
    src_ignored = _gitignore_skip(src[0].parent, project_dir)
    dest_ignored = _gitignore_skip(dest[0].parent, project_dir)
    # A link above either tree root leads every member elsewhere
    linked_root = any(
        _resolved_relative(root_abs.parent, project_dir)
        != Path(root_rel).parent.as_posix()
        for root_abs, root_rel in (src, dest)
    )

    for suffix in suffixes:
        src_abs, src_rel = _tree_member(src, suffix)
        if not src_ignored(src_abs):
            continue
        dest_abs, dest_rel = _tree_member(dest, suffix)
        if linked_root or _below_link(src_abs, src[0]):
            # A link can lead anywhere: judge every spelling in full
            src_hidden = _access(src_rel, project_dir, rules)[0] is FileAccess.HIDDEN
            dest_hidden = _access(dest_rel, project_dir, rules)[0] is FileAccess.HIDDEN
        else:
            src_hidden = _rule_access(src_rel, rules)[0] is None
            dest_hidden = (
                dest_ignored(dest_abs) and _rule_access(dest_rel, rules)[0] is None
            )
        if src_hidden and not dest_hidden:
            raise ValueError(
                f"Move refused: '{src[1]}' contains files hidden by .gitignore "
                f"rules that would become accessible at '{dest[1]}'"
            )


def check_tree_access(src_path: str, dest_path: str | None, project_dir: Path) -> None:
    """Raise ValueError if deleting or moving a tree would break the rules.

    Every file below src_path counts, including inside ignored
    subdirectories; a single file is a tree of one. Refused when a file's
    source path, or with dest_path its destination path, is read-only by
    rule, and for a move when a file hidden at its source would not be
    hidden at its destination. The destination is judged by the rules in
    effect before the move. Invalid or missing paths are left to the caller.

    Args:
        src_path: File or directory to delete or move, relative to project_dir.
        dest_path: Move destination, or None for a delete.
        project_dir: Project root directory.

    Raises:
        ValueError: If a file is read-only by rule, or the move would expose a
            hidden file; the latter message names no file.
    """  # noqa: DOC502 - raised by _check_not_read_only and _check_no_exposure
    try:
        src = normalize_path(src_path, project_dir)
        dest = None if dest_path is None else normalize_path(dest_path, project_dir)
    except ValueError:
        return
    if not src[0].exists() and not src[0].is_symlink():
        return

    rules = load_access_rules(project_dir)
    suffixes = [entry.relative_to(src[0]).as_posix() for entry in _tree_entries(src[0])]
    for suffix in suffixes:
        _check_not_read_only(_tree_member(src, suffix)[1], project_dir, rules)
        if dest is not None:
            _check_not_read_only(_tree_member(dest, suffix)[1], project_dir, rules)
    if dest is not None:
        _check_no_exposure(src, dest, suffixes, project_dir, rules)


_NOTE_READ_ONLY = "(read-only)"
_NOTE_NOT_COMMITTED = "(read-write, not committed)"


@dataclass(frozen=True)
class AccessListing:
    """What a listing walk reaches under .gitignore and ``.mcp-file-access``.

    Attributes:
        files: Project-relative paths, forward-slash separated, in walk order.
        notes: Path to ``(read-only)`` or ``(read-write, not committed)`` for
            files whose access differs from the default; empty when the rules
            file is invalid.
        problems: The rules file's problems; empty when it is valid.
    """

    files: list[str]
    notes: dict[str, str]
    problems: list[str]


def _exposes_dir(rel_dir: str, rules: AccessRules) -> bool:
    """Tell whether the walk may enter an ignored directory.

    Returns:
        True if a rule matches the directory itself or an anchored rule's
        literal prefix leads into it.
    """
    return rules.match(rel_dir, is_dir=True) is not None or rules.leads_into(rel_dir)


def _enterable(rel_dir: str, project_dir: Path, rules: AccessRules) -> bool:
    """Tell whether a listing walk from the root would reach a directory.

    Args:
        rel_dir: Project-relative directory with forward slashes, not ``.``.
        project_dir: Project root directory.
        rules: The project's rules, loaded once per tool call.

    Returns:
        False for ``.git`` and below, for a path through a link to a hidden
        location, and when an ignored directory on the path, rel_dir
        included, is not exposed by a rule; else True.
    """
    if is_path_in_git_dir(rel_dir):
        return False
    ancestor = ""
    for part in rel_dir.split("/"):
        ancestor = f"{ancestor}/{part}" if ancestor else part
        if (project_dir / ancestor).is_symlink() and _access(
            ancestor, project_dir, rules
        )[0] is FileAccess.HIDDEN:
            return False
        if is_path_gitignored(ancestor, project_dir) and not _exposes_dir(
            ancestor, rules
        ):
            return False
    return True


def _exposure_skip(
    start: Path, project_dir: Path, rules: AccessRules, notes: dict[str, str]
) -> Callable[[Path], bool]:
    """Build a skip predicate that lets the paths the rules expose through.

    Gitignore decides first. An ignored directory is entered only when
    ``_exposes_dir`` allows it; an ignored file is kept when a rule matches
    it. Only a link pays for the full multi-spelling ``_access`` check.

    Args:
        start: Absolute directory the walk starts at.
        project_dir: Project root directory.
        rules: The project's rules, loaded once per tool call.
        notes: Filled with the note of every kept entry that differs from the
            default; may hold directories, which the caller drops.

    Returns:
        A predicate that is True for an entry the listing leaves out.
    """
    ignored = _gitignore_skip(start, project_dir)

    def note(rel: str, is_ignored: bool) -> None:
        if rules.problems:
            return
        level = _rule_access(rel, rules)[0]
        if level is FileAccess.READ_ONLY:
            notes[rel] = _NOTE_READ_ONLY
        elif level is FileAccess.READ_WRITE and is_ignored:
            notes[rel] = _NOTE_NOT_COMMITTED

    def skip(path: Path) -> bool:
        rel = path.relative_to(project_dir).as_posix()
        if not ignored(path):
            note(rel, is_ignored=False)
            return False
        if path.is_dir():
            return not _exposes_dir(rel, rules)
        if _rule_access(rel, rules)[0] is None:
            return True
        # The built-in rule caps the rules file; it does not expose it
        if _is_rules_file(rel) and rules.match(rel) is None:
            return True
        if path.is_symlink() and (
            _access(rel, project_dir, rules)[0] is FileAccess.HIDDEN
        ):
            return True
        note(rel, is_ignored=True)
        return False

    return skip


def list_accessible_files(directory: str | Path, project_dir: Path) -> AccessListing:
    """List the files below a directory that effective access lets through.

    Like ``list_files``, plus the gitignored paths ``.mcp-file-access``
    exposes. The walk enters an ignored directory only when a rule matches it
    or an anchored rule's literal prefix leads into it, so a deep match of an
    unanchored rule is readable but not listed. The rules file is read once.

    Args:
        directory: Directory to list, relative to project_dir or absolute.
        project_dir: Project root directory.

    Returns:
        The files, their notes and the rules file's problems.

    Raises:
        ValueError: If the directory is hidden and the walk would not enter
            it, also when it does not exist, or is outside the project.
        FileNotFoundError: If the directory does not exist.
        NotADirectoryError: If the path is not a directory.
    """  # noqa: DOC501, DOC502 - _excluded_error and normalize_path raise ValueError
    abs_path, rel_path = normalize_path(str(directory), project_dir)
    rules = load_access_rules(project_dir)

    # Before the existence check, which would reveal whether a hidden path exists
    if rel_path != "." and not _enterable(rel_path, project_dir, rules):
        raise _excluded_error(str(directory))
    if not abs_path.exists():
        raise FileNotFoundError(f"Directory '{directory}' does not exist")
    if not abs_path.is_dir():
        raise NotADirectoryError(f"Path '{directory}' is not a directory")

    notes: dict[str, str] = {}
    files = _discover_files(
        abs_path, project_dir, _exposure_skip(abs_path, project_dir, rules, notes)
    )
    logger.debug("Discovered %s accessible files in %s", len(files), rel_path)
    return AccessListing(
        files=files,
        notes={rel: notes[rel] for rel in files if rel in notes},
        problems=list(rules.problems),
    )
