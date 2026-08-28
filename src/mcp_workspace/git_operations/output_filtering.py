"""Structure-aware output filtering for git diff and log output.

Provides search/filtering and truncation for git command output,
preserving structural elements like file headers and hunk boundaries.
"""

import re

from .compact_diffs import Hunk, parse_diff


def filter_diff_output(text: str, search: str, context: int = 3) -> str:
    """Structure-aware diff filtering.

    Parses the diff, finds hunks with lines matching the search pattern,
    and returns matching hunks with file/hunk headers preserved.

    Args:
        text: Raw unified diff text.
        search: Regex pattern to search for (case-insensitive).
        context: Number of lines before/after each match within a hunk.

    Returns:
        Filtered diff fragment, or a descriptive message if no matches found.
    """
    files = parse_diff(text)
    try:
        pattern = re.compile(search, re.IGNORECASE)
    except re.error as e:
        return f"Invalid search pattern: {e}"

    output_parts: list[str] = []

    for file_diff in files:
        matching_hunks = _filter_hunks(file_diff.hunks, pattern, context)
        if matching_hunks:
            parts = list(file_diff.headers)
            for hunk_header, hunk_lines in matching_hunks:
                parts.append(hunk_header)
                parts.extend(hunk_lines)
            output_parts.append("\n".join(parts))

    if not output_parts:
        return f"No matches for search pattern '{search}'"

    return "\n".join(output_parts)


def _filter_hunks(
    hunks: list[Hunk], pattern: re.Pattern[str], context: int
) -> list[tuple[str, list[str]]]:
    """Return matching hunks with context-filtered lines.

    Args:
        hunks: List of Hunk objects to filter.
        pattern: Compiled regex pattern.
        context: Lines of context around each match.

    Returns:
        List of (header, lines) tuples for hunks containing matches.
    """
    result: list[tuple[str, list[str]]] = []

    for hunk in hunks:
        matching_indices: list[int] = []
        for i, line in enumerate(hunk.lines):
            if pattern.search(line):
                matching_indices.append(i)

        if not matching_indices:
            continue

        # Collect line indices to include (matches + context)
        include: set[int] = set()
        for idx in matching_indices:
            start = max(0, idx - context)
            end = min(len(hunk.lines), idx + context + 1)
            for j in range(start, end):
                include.add(j)

        kept_lines = [hunk.lines[i] for i in sorted(include) if i < len(hunk.lines)]
        result.append((hunk.header, kept_lines))

    return result


def filter_content_output(text: str, search: str, context: int = 3) -> str:
    """Line-based grep for plain content (not a diff).

    Returns lines matching `search` (case-insensitive) plus `context` lines
    before/after each match. Non-adjacent regions are separated by a ``--``
    line (grep-style). Sibling to filter_diff_output / filter_log_output.

    Args:
        text: Plain text content (e.g. from git show HEAD:<file>).
        search: Regex pattern to search for (case-insensitive).
        context: Number of lines before/after each match.

    Returns:
        Matching lines with context, or a descriptive message if no matches found.
    """
    try:
        pattern = re.compile(search, re.IGNORECASE)
    except re.error as e:
        return f"Invalid search pattern: {e}"

    lines = text.splitlines()
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if pattern.search(line):
            keep.update(range(max(0, i - context), min(len(lines), i + context + 1)))

    if not keep:
        return f"No matches for search pattern '{search}'"

    result_lines: list[str] = []
    prev = -2
    for i in sorted(keep):
        if prev >= 0 and i > prev + 1:
            result_lines.append("--")
        result_lines.append(lines[i])
        prev = i
    return "\n".join(result_lines)


def filter_log_output(text: str, search: str) -> str:
    """Structure-aware log filtering.

    Splits log text into commit entries and returns entire entries
    that match the search pattern.

    Args:
        text: Raw git log output.
        search: Regex pattern to search for (case-insensitive).

    Returns:
        Matching commit entries, or a descriptive message if no matches found.
    """
    try:
        pattern = re.compile(search, re.IGNORECASE)
    except re.error as e:
        return f"Invalid search pattern: {e}"
    commit_re = re.compile(r"^commit [0-9a-f]{7,}", re.MULTILINE)

    # Split into commit entries
    splits = list(commit_re.finditer(text))
    if not splits:
        # No commit entries found; search the whole text
        if pattern.search(text):
            return text
        return f"No matches for search pattern '{search}'"

    entries: list[str] = []
    for i, match in enumerate(splits):
        start = match.start()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        entries.append(text[start:end].rstrip())

    kept = [entry for entry in entries if pattern.search(entry)]

    if not kept:
        return f"No matches for search pattern '{search}'"

    return "\n\n".join(kept)


def truncate_output(text: str, max_lines: int) -> str:
    """Truncate text to max_lines.

    Args:
        text: Text to truncate.
        max_lines: Maximum number of lines to keep.

    Returns:
        Original text if within limit, otherwise truncated text with
        a notice stating the applied cap, the total line count and the
        max_lines value that returns the full output.
    """
    if not text:
        return text

    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text

    kept = lines[:max_lines]
    total = len(lines)
    kept.append(
        f"[truncated: showing {max_lines} of {total} lines "
        f"— pass max_lines={total} for the full output]"
    )
    return "\n".join(kept)
