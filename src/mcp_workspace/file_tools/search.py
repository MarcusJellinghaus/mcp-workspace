"""File search utilities for glob matching and content searching."""

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pathspec import PathSpec, RegexPattern

from mcp_workspace.file_tools.directory_utils import list_files
from mcp_workspace.file_tools.path_utils import normalize_path

# Deliberate internal cap with no lift parameter: search_files returns many
# lines and a single pathological line must not crowd out the rest. Callers
# who need a full line read the file at the reported line number.
_MAX_LINE_CHARS = 500

# Braces are the one silent-zero case that cannot raise: gitwildmatch compiles
# them to a valid regex matching them literally, and directories literally named
# '{{cookiecutter.project_slug}}' are real. Detection is textual, so the caller
# gets a note rather than an error.
_BRACE_NOTE = (
    "Glob matched no files and contains '{'. Brace expansion is not supported — "
    "patterns use gitignore/wildmatch semantics, where braces are literal. "
    "Issue one call per alternative, or widen to '*' and filter the results."
)


def _glob_note(glob: str) -> Optional[str]:
    """Explain a zero-match glob when its braces are the likely cause.

    Args:
        glob: Glob pattern that matched no files.

    Returns:
        ``_BRACE_NOTE`` if the pattern contains a brace, else ``None``.
    """
    return _BRACE_NOTE if "{" in glob else None


def _match_glob(glob: str, files: List[str]) -> List[str]:
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
    """
    win32 = sys.platform == "win32"
    spec = PathSpec.from_lines("gitwildmatch", [glob.lower() if win32 else glob])

    usable = any(
        isinstance(p, RegexPattern) and p.regex is not None and p.include
        for p in spec.patterns
    )
    if not usable:
        raise ValueError(
            f"Glob pattern {glob!r} matches nothing by construction "
            "(gitignore comment, blank, negation-only, or unparseable pattern)"
        )

    def _norm(p: str) -> str:
        slashed = p.replace("\\", "/")
        return slashed.lower() if win32 else slashed

    return [f for f in files if spec.match_file(_norm(f))]


def _search_content(
    files: List[str],
    compiled: "re.Pattern[str]",
    project_dir: Path,
    context_lines: int,
    max_results: int,
    max_result_lines: int,
) -> Dict[str, Any]:
    """Search file contents for regex matches.

    Returns:
        content_search result dict.
    """
    matches: List[Dict[str, Any]] = []
    total_matches = 0
    char_budget = max_result_lines * 120
    chars_used = 0
    truncated = False
    files_map: Dict[str, List[int]] = {}

    for rel_path in files:
        abs_path, _ = normalize_path(rel_path, project_dir)
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                file_lines = f.readlines()
        except UnicodeDecodeError:
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

    result: Dict[str, Any] = {
        "mode": "content_search",
        "details": matches,
        "total_matches": total_matches,
        "truncated": truncated,
    }
    if truncated:
        result["matched_files"] = [
            {"file": f, "lines": lns} for f, lns in files_map.items()
        ]
    return result


def search_files(
    project_dir: Path,
    glob: Optional[str] = None,
    pattern: Optional[str] = None,
    context_lines: int = 0,
    max_results: int = 50,
    max_result_lines: int = 200,
) -> Dict[str, Any]:
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

    Raises:
        ValueError: If neither glob nor pattern is provided, or if the glob
            matches nothing by construction (gitignore comment, blank,
            negation-only, or unparseable pattern).
    """
    if glob is None and pattern is None:
        raise ValueError("At least one of 'glob' or 'pattern' must be provided")

    all_files = list_files(".", project_dir=project_dir, use_gitignore=True)

    matched = _match_glob(glob, all_files) if glob is not None else all_files
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
            project_dir,
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

    file_result: Dict[str, Any] = {
        "mode": "file_search",
        "files": matched[:max_results],
        "total_files": total,
        "truncated": truncated,
    }
    if glob_note is not None:
        file_result["glob_note"] = glob_note

    return file_result
