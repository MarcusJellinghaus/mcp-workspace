"""File search utilities for glob matching and content searching."""

import functools
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pathspec import GitIgnoreSpec, RegexPattern

from mcp_workspace.file_tools.access_rules import GlobPattern, access_rules_warning
from mcp_workspace.file_tools.file_access import list_accessible_files
from mcp_workspace.file_tools.path_utils import normalize_path

# Deliberate internal cap with no lift parameter: search_files returns many
# lines and a single pathological line must not crowd out the rest. Callers
# who need a full line read the file at the reported line number.
_MAX_LINE_CHARS = 500

# Braces are the one silent-zero case that cannot raise: gitignore semantics compile
# them to a valid regex matching them literally, and directories literally named
# '{{cookiecutter.project_slug}}' are real. Detection is textual, so the caller
# gets a note rather than an error.
_BRACE_NOTE = (
    "Glob matched no files and contains '{'. Brace expansion is not supported — "
    "patterns use gitignore/wildmatch semantics, where braces are literal. "
    "Issue one call per alternative, or widen to '*' and filter the results."
)


def _glob_note(glob: str) -> str | None:
    """Explain a zero-match glob when its braces are the likely cause.

    Args:
        glob: Glob pattern that matched no files.

    Returns:
        ``_BRACE_NOTE`` if the pattern contains a brace, else ``None``.
    """
    return _BRACE_NOTE if "{" in glob else None


def _nothing_matches(glob: str) -> ValueError:
    """Build the error for a glob that cannot match anything.

    Returns:
        The error to raise, naming glob.
    """
    return ValueError(
        f"Glob pattern {glob!r} matches nothing by construction "
        "(gitignore comment, blank, negation-only, or unparseable pattern)"
    )


def _match_glob(glob: str, files: list[str]) -> list[str]:
    """Match project-relative paths against a gitignore-semantics glob.

    Args:
        glob: Glob pattern, interpreted with gitignore/wildmatch semantics.
        files: Project-relative paths to filter.

    Returns:
        The subset of ``files`` matching ``glob``.

    Raises:
        ValueError: If the pattern cannot match anything by construction —
            a gitignore comment, a blank line, a negation-only pattern, or a
            pattern pathspec cannot compile (such as an unterminated ``[``).
    """  # noqa: DOC501, DOC502 - _nothing_matches returns the documented ValueError
    try:
        spec = GitIgnoreSpec.from_lines([glob], GlobPattern)
    except re.error as exc:
        raise _nothing_matches(glob) from exc

    usable = any(
        isinstance(p, RegexPattern) and p.regex is not None and p.include
        for p in spec.patterns
    )
    if not usable:
        raise _nothing_matches(glob)

    return [f for f in files if spec.match_file(f)]


def _search_content(
    files: list[str],
    compiled: "re.Pattern[str]",
    read_lines: Callable[[str], list[str]],
    context_lines: int,
    max_results: int,
    max_result_lines: int,
) -> dict[str, Any]:
    """Search file contents for regex matches.

    Args:
        files: Paths to search, in result order.
        compiled: Compiled content pattern.
        read_lines: Returns the lines of one path. ``UnicodeDecodeError`` is a
            silent skip; any other ``ValueError`` or ``OSError`` reports the
            path in ``skipped_files``.
        context_lines: Number of context lines around matches.
        max_results: Maximum number of results to return.
        max_result_lines: Maximum total lines in result output.

    Returns:
        content_search result dict. Carries a ``skipped_files`` key listing
        project-relative paths that could not be read — a path rejected by the
        security check, or an unreadable file — present only when non-empty.
    """
    matches: list[dict[str, Any]] = []
    total_matches = 0
    char_budget = max_result_lines * 120
    chars_used = 0
    truncated = False
    files_map: dict[str, list[int]] = {}
    skipped: list[str] = []

    for rel_path in files:
        try:
            file_lines = read_lines(rel_path)
        except UnicodeDecodeError:
            # Must precede the next handler: UnicodeDecodeError is a subclass
            # of ValueError. Binary files stay a silent skip.
            continue
        except (ValueError, OSError):
            skipped.append(rel_path)
            continue

        for i, line in enumerate(file_lines):
            if not compiled.search(line):
                continue

            total_matches += 1
            files_map.setdefault(rel_path, []).append(i + 1)

            # Check if we've already hit the caps for returned matches
            if truncated:
                continue

            start = max(0, i - context_lines)
            end = min(len(file_lines), i + context_lines + 1)
            raw_lines = file_lines[start:end]
            capped = []
            for raw in raw_lines:
                stripped = raw.rstrip("\n")
                if len(stripped) > _MAX_LINE_CHARS:
                    stripped = (
                        stripped[:_MAX_LINE_CHARS]
                        + f" ... [line truncated: showing {_MAX_LINE_CHARS}"
                        f" of {len(stripped)} chars]"
                    )
                capped.append(stripped)
            context = "\n".join(capped)

            if len(matches) >= max_results or chars_used + len(context) > char_budget:
                truncated = True
                continue

            matches.append({"file": rel_path, "line": i + 1, "text": context})
            chars_used += len(context)

    result: dict[str, Any] = {
        "mode": "content_search",
        "details": matches,
        "total_matches": total_matches,
        "truncated": truncated,
    }
    if truncated:
        result["matched_files"] = [
            {"file": f, "lines": lns} for f, lns in files_map.items()
        ]
    if skipped:
        result["skipped_files"] = skipped
    return result


def _read_local_lines(project_dir: Path, rel_path: str) -> list[str]:
    """Read one working-tree file as UTF-8 lines.

    Args:
        project_dir: Project root directory.
        rel_path: Project-relative path.

    Returns:
        The file's lines, newlines kept.
    """
    abs_path, _ = normalize_path(rel_path, project_dir)
    with open(abs_path, encoding="utf-8") as f:
        return f.readlines()


def search_paths(
    files: list[str],
    read_lines: Callable[[str], list[str]],
    glob: str | None = None,
    pattern: str | None = None,
    context_lines: int = 0,
    max_results: int = 50,
    max_result_lines: int = 200,
) -> dict[str, Any]:
    """Search a given file list by glob and/or content regex.

    The engine behind ``search_files``, on an injected file list and reader.

    Args:
        files: Relative, forward-slash paths to consider, in result order.
        read_lines: Returns the lines of one path, newlines kept. Raising
            ``UnicodeDecodeError`` skips the path silently; any other
            ``ValueError`` or ``OSError`` reports it in ``skipped_files``.
        glob: Glob pattern with gitignore/wildmatch semantics; see
            ``search_files``.
        pattern: Python regex to match file contents. Invalid regex patterns
            are automatically treated as literal text.
        context_lines: Number of context lines around matches.
        max_results: Maximum number of results to return.
        max_result_lines: Maximum total lines in result output.

    Returns:
        Dictionary with search results, with the same keys as
        ``search_files``.

    Raises:
        ValueError: If neither glob nor pattern is provided, or if the glob
            matches nothing by construction (gitignore comment, blank,
            negation-only, or unparseable pattern).
    """
    if glob is None and pattern is None:
        raise ValueError("At least one of 'glob' or 'pattern' must be provided")

    matched = _match_glob(glob, files) if glob is not None else files
    glob_note = _glob_note(glob) if glob is not None and not matched else None

    # Content search mode: pattern provided
    if pattern is not None:
        try:
            compiled = re.compile(pattern)
            note = None
        except re.error:
            compiled = re.compile(re.escape(pattern))
            note = (
                "Pattern treated as literal text (invalid regex). "
                "Use Python re syntax for regex search."
            )

        result = _search_content(
            matched,
            compiled,
            read_lines,
            context_lines,
            max_results,
            max_result_lines,
        )

        if note is not None:
            result["note"] = note
        if glob_note is not None:
            result["glob_note"] = glob_note

        return result

    # File search mode: glob only
    total = len(matched)
    truncated = total > max_results

    file_result: dict[str, Any] = {
        "mode": "file_search",
        "files": matched[:max_results],
        "total_files": total,
        "truncated": truncated,
    }
    if glob_note is not None:
        file_result["glob_note"] = glob_note

    return file_result


def search_files(
    project_dir: Path,
    glob: str | None = None,
    pattern: str | None = None,
    context_lines: int = 0,
    max_results: int = 50,
    max_result_lines: int = 200,
) -> dict[str, Any]:
    """Search file contents by regex and/or find files by glob pattern.

    Args:
        project_dir: Project root directory.
        glob: Glob pattern with gitignore/wildmatch semantics. Examples:
            ``*.py`` (unanchored — any .py at any depth, unlike a shell
            glob), ``tests/**/test_*.py``, ``/README.md`` (root only).
            Brace expansion is NOT supported: ``{a,b}/f.py`` matches a
            literal ``{a,b}`` directory. Issue one call per alternative, or
            widen to ``*`` and filter. On Windows, matching is
            case-insensitive by design, so a glob cannot detect a filename
            casing mismatch — use ``git ls-files``, which reports the name as
            recorded in the index.
        pattern: Python regex to match file contents. Invalid regex patterns
            are automatically treated as literal text.
            (e.g. "def foo", "TODO.*fix")
        context_lines: Number of context lines around matches.
        max_results: Maximum number of results to return.
        max_result_lines: Maximum total lines in result output.

    Returns:
        Dictionary with search results. Carries a ``glob_note`` key when the
        glob matched no files and contains ``{``, which wildmatch treats
        literally, distinguishing that from a genuine no-such-file result.
        A content search carries a ``skipped_files`` key listing
        project-relative paths that could not be read — a path rejected by the
        security check, or an unreadable file — present only when non-empty.
        Carries a "warning" key with the invalid-rules warning while
        .mcp-file-access is invalid.

    Raises:
        ValueError: If neither glob nor pattern is provided, or if the glob
            matches nothing by construction (gitignore comment, blank,
            negation-only, or unparseable pattern).
    """
    if glob is None and pattern is None:
        raise ValueError("At least one of 'glob' or 'pattern' must be provided")

    # Includes the gitignored paths .mcp-file-access exposes, unmarked
    listing = list_accessible_files(".", project_dir)
    all_files = listing.files
    warning = access_rules_warning(listing.problems)

    result = search_paths(
        all_files,
        functools.partial(_read_local_lines, project_dir),
        glob,
        pattern,
        context_lines,
        max_results,
        max_result_lines,
    )
    if warning is not None:
        result["warning"] = warning

    return result
