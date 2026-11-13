"""Parse and match the ``.mcp-file-access`` rules file.

Each non-comment line is ``<level> <gitignore pattern>``; the last matching
rule wins. An invalid file yields its problems and no rules, so callers fail
safe. The file is re-read on every call; nothing is cached.
"""

import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pathspec import PathSpec, Pattern

logger = logging.getLogger(__name__)

ACCESS_RULES_FILE = ".mcp-file-access"
READ_ONLY = "read-only"
READ_WRITE = "read-write"

_LEVELS = (READ_ONLY, READ_WRITE)
_GLOB_CHARS = ("*", "?", "[", "\\")

# Problems already logged, keyed by project directory and problem text, so a
# rules file re-read on every tool call warns once per distinct problem.
_reported: set[str] = set()


def _fold(text: str) -> str:
    """Lower-case text on win32, where path matching ignores case.

    Args:
        text: Pattern or path to fold.

    Returns:
        ``text`` lower-cased on win32, unchanged elsewhere.
    """
    return text.lower() if sys.platform == "win32" else text


def _literal_prefix(pattern: str) -> str:
    """Return the leading path segments of an anchored pattern without globs.

    Args:
        pattern: A rule pattern as written in the rules file.

    Returns:
        The segments before the first one containing a glob character,
        joined by ``/``; empty when the pattern is unanchored (no ``/`` other
        than a trailing one) or starts with a glob.
    """
    if "/" not in pattern.rstrip("/"):
        return ""
    prefix: list[str] = []
    for segment in pattern.strip("/").split("/"):
        if any(char in segment for char in _GLOB_CHARS):
            break
        prefix.append(segment)
    return "/".join(prefix)


@dataclass(frozen=True)
class AccessRule:
    """One parsed line of the rules file."""

    level: str
    pattern: str
    line: int


@dataclass(frozen=True)
class AccessRules:
    """Parsed rules file: its rules in file order, or the problems found."""

    rules: tuple[AccessRule, ...] = ()
    problems: tuple[str, ...] = ()
    _spec: PathSpec[Pattern] | None = field(default=None, compare=False, repr=False)

    def match(self, rel_path: str, is_dir: bool = False) -> AccessRule | None:
        """Return the last rule matching a project-relative path.

        Args:
            rel_path: Project-relative path with forward slashes.
            is_dir: Whether the path is a directory, so directory-only
                patterns (trailing ``/``) can match it.

        Returns:
            The winning rule, or ``None`` when no rule matches.
        """
        if self._spec is None:
            return None
        path = rel_path + "/" if is_dir else rel_path
        index = self._spec.check_file(_fold(path)).index
        return self.rules[index] if index is not None else None

    def leads_into(self, rel_dir: str) -> bool:
        """Tell whether an anchored rule's literal prefix reaches a directory.

        Args:
            rel_dir: Project-relative directory with forward slashes.

        Returns:
            True if some anchored rule's literal prefix equals ``rel_dir`` or
            lies below it, so paths the rule exposes may sit inside it.
        """
        folded = _fold(rel_dir)
        for rule in self.rules:
            prefix = _fold(_literal_prefix(rule.pattern))
            if prefix and (prefix == folded or prefix.startswith(folded + "/")):
                return True
        return False


def _compiles(pattern: str) -> bool:
    """Tell whether a gitignore pattern compiles to something that matches.

    Args:
        pattern: A rule pattern as written in the rules file.

    Returns:
        False if pathspec rejects the pattern or compiles it to nothing
        (a comment), else True.
    """
    try:
        spec = PathSpec.from_lines("gitignore", [pattern])
    except ValueError:
        return False
    return all(p.regex is not None for p in spec.patterns)


def _parse_line(number: int, line: str) -> AccessRule | str:
    """Parse one non-blank, non-comment line into a rule or a problem.

    Args:
        number: 1-based line number.
        line: The stripped line.

    Returns:
        The parsed rule, or a problem description naming the line.
    """
    parts = line.split(maxsplit=1)
    if len(parts) != 2:
        return f"line {number}: expected '<level> <pattern>'"
    level, pattern = parts
    if level not in _LEVELS:
        return f"line {number}: unknown level '{level}'"
    if pattern.startswith("!"):
        return f"line {number}: negation '!' is not allowed"
    if not _compiles(pattern):
        return f"line {number}: invalid pattern '{pattern}'"
    return AccessRule(level=level, pattern=pattern, line=number)


def _read_text(rules_file: Path) -> tuple[str | None, str | None]:
    """Read the rules file.

    Args:
        rules_file: Path of the rules file.

    Returns:
        ``(text, None)`` when readable, ``(None, problem)`` when not, and
        ``(None, None)`` when the file is absent.
    """
    if rules_file.is_dir():
        return None, "is a directory"
    try:
        data = rules_file.read_bytes()
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, f"cannot be read: {exc}"
    try:
        # utf-8-sig: a byte order mark (Windows editors) must not corrupt line 1.
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return None, "is not valid UTF-8"


def _report(project_dir: Path, problems: Sequence[str]) -> None:
    """Log each problem once per project directory."""
    for problem in problems:
        key = f"{project_dir}: {problem}"
        if key not in _reported:
            _reported.add(key)
            logger.warning(
                "%s in %s is invalid: %s", ACCESS_RULES_FILE, project_dir, problem
            )


def load_access_rules(project_dir: Path) -> AccessRules:
    """Load the rules file from the project root.

    Args:
        project_dir: Project root directory.

    Returns:
        The parsed rules; empty when the file is absent. When the file is
        invalid, ``problems`` lists every problem and ``rules`` is empty.
    """
    text, problem = _read_text(project_dir / ACCESS_RULES_FILE)
    problems: list[str] = [problem] if problem else []
    rules: list[AccessRule] = []
    for number, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parsed = _parse_line(number, line)
        if isinstance(parsed, str):
            problems.append(parsed)
        else:
            rules.append(parsed)

    if problems:
        _report(project_dir, problems)
        return AccessRules(problems=tuple(problems))
    if not rules:
        return AccessRules()
    spec = PathSpec.from_lines("gitignore", [_fold(r.pattern) for r in rules])
    return AccessRules(rules=tuple(rules), _spec=spec)


def validate_access_rules(project_dir: Path) -> list[str]:
    """Return the problems of the project's rules file.

    Args:
        project_dir: Project root directory.

    Returns:
        Problem descriptions; empty when the file is absent or valid.
    """
    return list(load_access_rules(project_dir).problems)


def access_rules_warning(problems: Sequence[str]) -> str | None:
    """Build the warning line shown when the rules file is invalid.

    Args:
        problems: Problems reported by ``load_access_rules``.

    Returns:
        The warning line, or ``None`` when there are no problems.
    """
    if not problems:
        return None
    return (
        f"WARNING: {ACCESS_RULES_FILE} is invalid ({'; '.join(problems)})"
        " - writes are refused and no gitignored path is exposed."
    )
