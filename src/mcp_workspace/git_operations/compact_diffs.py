"""Compact diff pipeline: suppress moved-code blocks to reduce diff size."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .diffs import get_branch_diff

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_CONTENT_LENGTH: int = 10  # ignore short lines like "pass", "}" when matching moves
MIN_BLOCK_LINES: int = 5  # minimum block size to suppress (3 is too aggressive)
PREVIEW_LINES: int = 3  # non-blank lines to show before the summary comment

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Hunk:
    """Represents a single unified diff hunk."""

    header: str  # raw "@@ -a,b +c,d @@" line
    lines: list[str] = field(default_factory=list)


@dataclass
class FileDiff:
    """Represents the diff for a single file."""

    headers: list[str] = field(
        default_factory=list
    )  # "diff --git ...", "index ...", etc.
    hunks: list[Hunk] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Layer 1: Parsing
# ---------------------------------------------------------------------------


def parse_diff(text: str) -> list[FileDiff]:
    """Parse a plain unified diff string into FileDiff/Hunk objects.

    Args:
        text: Raw unified diff string

    Returns:
        List of FileDiff objects, one per file in the diff. Empty list if input is blank.
    """
    files: list[FileDiff] = []
    if not text.strip():
        return files

    current_file: FileDiff | None = None
    current_hunk: Hunk | None = None

    for line in text.splitlines():
        if line.startswith("diff --git"):
            # Save previous hunk/file
            if current_hunk is not None and current_file is not None:
                current_file.hunks.append(current_hunk)
                current_hunk = None
            if current_file is not None:
                files.append(current_file)
            current_file = FileDiff(headers=[line])
        elif current_file is not None and line.startswith("@@"):
            # Start a new hunk
            if current_hunk is not None:
                current_file.hunks.append(current_hunk)
            current_hunk = Hunk(header=line)
        elif current_hunk is not None:
            current_hunk.lines.append(line)
        elif current_file is not None:
            # File header lines (index, ---, +++)
            current_file.headers.append(line)

    # Flush last hunk and file
    if current_hunk is not None and current_file is not None:
        current_file.hunks.append(current_hunk)
    if current_file is not None:
        files.append(current_file)

    return files


# ---------------------------------------------------------------------------
# Layer 2: ANSI detection (Pass 1)
# ---------------------------------------------------------------------------

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from a string.

    Args:
        text: String potentially containing ANSI escape codes

    Returns:
        String with all ANSI escape sequences removed.
    """
    return _ANSI_ESCAPE_RE.sub("", text)


def is_moved_line(raw_line: str) -> bool:
    r"""True if the ANSI-coloured diff line is classified as moved by git.

    Looks for the 'dim' SGR attribute (code 2) in the ANSI codes.
    Only +/- lines can be moved; context lines and headers return False.

    Returns:
        True if the line has ANSI dim attribute (SGR code 2) indicating a moved line,
        False for context lines, headers, or non-moved +/- lines.

    Note: ANSI dim codes (\x1b[2m) are confirmed to work on Windows —
    no special environment setup is required.
    """
    plain = strip_ansi(raw_line)
    if not plain or plain[0] not in ("+", "-"):
        return False
    # Look for SGR code 2 (dim) in the ANSI sequences of this line.
    # Assumption: SGR 2 (dim) reliably identifies moved lines when using
    # --color-moved=dimmed-zebra. Other uses of SGR 2 in a diff line are
    # not expected in practice.
    codes_found = set()
    for match in _ANSI_ESCAPE_RE.finditer(raw_line):
        seq = match.group()
        # Strip \x1b[ and trailing m, split by ;
        inner = seq[2:-1]
        for code in inner.split(";"):
            codes_found.add(code)
    return "2" in codes_found


def extract_moved_blocks_ansi(ansi_diff: str) -> set[str]:
    """Return the set of stripped line contents that git marked as moved.

    Uses is_moved_line() per line to identify lines coloured with ANSI dim
    by --color-moved=dimmed-zebra.

    Args:
        ansi_diff: Diff output with ANSI colour codes

    Returns:
        Set of stripped content strings (without +/- prefix) for lines marked as moved.
    """
    moved: set[str] = set()
    for line in ansi_diff.splitlines():
        if is_moved_line(line):
            plain = strip_ansi(line)
            # Strip the leading +/- sign and trailing whitespace, then add content
            content = plain[1:].strip()
            moved.add(content)
    return moved


# ---------------------------------------------------------------------------
# Layer 3: Python cross-file matching (Pass 2)
# ---------------------------------------------------------------------------


def is_significant_line(content: str) -> bool:
    """True if stripped content length >= MIN_CONTENT_LENGTH.

    Args:
        content: Line content to check

    Returns:
        True if the stripped content is at least MIN_CONTENT_LENGTH characters,
        False for short lines like "pass" or "}".
    """
    return len(content.strip()) >= MIN_CONTENT_LENGTH


def collect_line_occurrences(files: list[FileDiff]) -> tuple[set[str], set[str]]:
    """Return (removed_lines, added_lines) sets of significant stripped content.

    Args:
        files: List of parsed FileDiff objects

    Returns:
        Tuple of (removed_lines, added_lines) where each is a set of stripped
        content strings from significant - and + lines respectively.
    """
    removed: set[str] = set()
    added: set[str] = set()
    for file_diff in files:
        for hunk in file_diff.hunks:
            for line in hunk.lines:
                if line.startswith("-"):
                    content = line[1:].strip()
                    if is_significant_line(content):
                        removed.add(content)
                elif line.startswith("+"):
                    content = line[1:].strip()
                    if is_significant_line(content):
                        added.add(content)
    return removed, added


def find_moved_lines(files: list[FileDiff]) -> set[str]:
    """Return intersection of removed and added significant lines = moved.

    Args:
        files: List of parsed FileDiff objects

    Returns:
        Set of stripped content strings that appear in both removed and added lines,
        indicating code that was moved rather than truly added or deleted.
    """
    removed, added = collect_line_occurrences(files)
    return removed & added


def collect_line_sources(
    files: list[FileDiff],
) -> tuple[dict[str, str], dict[str, str]]:
    """Return (removed_to_file, added_to_file) mappings of content -> filename.

    For each significant line, records the last file that removed or added it.
    Used to annotate moved-block summaries with source/destination file names:
    - removed_to_file: look up when rendering a + block to show 'moved from'
    - added_to_file:   look up when rendering a - block to show 'moved to'

    Args:
        files: List of parsed FileDiff objects

    Returns:
        Tuple of (removed_to_file, added_to_file) dictionaries mapping stripped
        content strings to the filename where they were last removed or added.
    """
    removed_to_file: dict[str, str] = {}
    added_to_file: dict[str, str] = {}
    for file_diff in files:
        filename = (
            (file_diff.headers[0].split() or [""])[-1] if file_diff.headers else ""
        )
        if not filename:
            continue
        for hunk in file_diff.hunks:
            for line in hunk.lines:
                if line.startswith("-"):
                    content = line[1:].strip()
                    if is_significant_line(content):
                        removed_to_file[content] = filename
                elif line.startswith("+"):
                    content = line[1:].strip()
                    if is_significant_line(content):
                        added_to_file[content] = filename
    return removed_to_file, added_to_file


# ---------------------------------------------------------------------------
# Layer 4: Block analysis
# ---------------------------------------------------------------------------


def format_moved_summary(
    count: int,
    ref_file: str | None = None,
    is_addition: bool = True,
) -> str:
    """Return a moved-block summary comment.

    Without ref_file: '# [moved: N lines not shown]'
    With ref_file and is_addition=True  (+ block): '# [moved from ref_file: N lines not shown]'
    With ref_file and is_addition=False (- block): '# [moved to ref_file: N lines not shown]'

    Args:
        count: Number of suppressed lines
        ref_file: Optional source/destination filename for annotation
        is_addition: True for + blocks (moved from), False for - blocks (moved to)

    Returns:
        Formatted summary comment string describing the moved block.
    """
    if ref_file:
        direction = "from" if is_addition else "to"
        return f"# [moved {direction} {ref_file}: {count} lines not shown]"
    return f"# [moved: {count} lines not shown]"


# ---------------------------------------------------------------------------
# Layer 5: Rendering
# ---------------------------------------------------------------------------


def _find_preview_split(lines: list[str], n: int) -> int:
    """Return the index after the nth non-blank content line, or len(lines) if fewer.

    Args:
        lines: List of diff lines (with +/- prefix)
        n: Number of non-blank content lines to find

    Returns:
        Index after the nth non-blank content line, or len(lines) if fewer exist.
    """
    non_blank_count = 0
    for i, line in enumerate(lines):
        if line[1:].strip():  # non-blank after the +/- prefix
            non_blank_count += 1
            if non_blank_count >= n:
                return i + 1
    return len(lines)


def _flush_sub_block(
    sub_block: list[str],
    moved_lines: set[str],
    removed_to_file: dict[str, str] | None = None,
    added_to_file: dict[str, str] | None = None,
) -> list[str]:
    """Emit sub_block as a moved summary if large enough, otherwise as-is.

    A sub_block qualifies for suppression when it has >= MIN_BLOCK_LINES lines
    and contains at least one significant moved line. Because _render_block()
    only accumulates lines that are not non-moved-significant, every significant
    line in the sub_block is guaranteed to be in moved_lines.

    When removed_to_file / added_to_file are provided, annotates the summary
    with the source or destination filename.

    Args:
        sub_block: Consecutive same-sign diff lines to evaluate
        moved_lines: Set of content strings identified as moved
        removed_to_file: Mapping of removed content to source filename
        added_to_file: Mapping of added content to destination filename

    Returns:
        List of output lines, either the original sub_block lines or a
        preview plus summary comment if the block qualifies for suppression.
    """
    if not sub_block:
        return []
    significant_moved = [
        bl
        for bl in sub_block
        if is_significant_line(bl[1:]) and bl[1:].strip() in moved_lines
    ]
    if len(sub_block) >= MIN_BLOCK_LINES and significant_moved:
        is_addition = sub_block[0].startswith("+")
        ref_file: str | None = None
        source_map = removed_to_file if is_addition else added_to_file
        if source_map is not None:
            for bl in significant_moved:
                candidate = source_map.get(bl[1:].strip())
                if candidate:
                    ref_file = candidate
                    break
        # Show the first PREVIEW_LINES non-blank lines so the reader can see
        # which function/class was moved, then summarise the rest.
        split_idx = _find_preview_split(sub_block, PREVIEW_LINES)
        preview = sub_block[:split_idx]
        remainder = sub_block[split_idx:]
        if not remainder:
            return list(sub_block)  # everything fits in preview
        sign = "+" if is_addition else "-"
        return preview + [
            sign + format_moved_summary(len(remainder), ref_file, is_addition)
        ]
    return list(sub_block)


def _render_block(
    block: list[str],
    moved_lines: set[str],
    removed_to_file: dict[str, str] | None = None,
    added_to_file: dict[str, str] | None = None,
) -> list[str]:
    """Render a consecutive same-sign block, suppressing moved sub-sections.

    Splits the block at non-moved significant lines (which are always emitted).
    Each segment between splits is passed to _flush_sub_block(), which replaces
    it with a summary comment if it is long enough and all its significant lines
    are moved. This allows moved blocks in new files to be suppressed even when
    the file has a different header or imports above the moved content.

    Args:
        block: Consecutive same-sign (+/-) diff lines
        moved_lines: Set of content strings identified as moved
        removed_to_file: Mapping of removed content to source filename
        added_to_file: Mapping of added content to destination filename

    Returns:
        List of rendered output lines with moved sub-sections replaced by
        summary comments where applicable.
    """
    output: list[str] = []
    sub_block: list[str] = []
    for line in block:
        content = line[1:].strip()
        if is_significant_line(content) and content not in moved_lines:
            # Non-moved significant line: flush accumulated sub-block, emit this line
            output.extend(
                _flush_sub_block(sub_block, moved_lines, removed_to_file, added_to_file)
            )
            sub_block = []
            output.append(line)
        else:
            sub_block.append(line)
    output.extend(
        _flush_sub_block(sub_block, moved_lines, removed_to_file, added_to_file)
    )
    return output


def render_hunk(
    hunk: Hunk,
    moved_lines: set[str],
    removed_to_file: dict[str, str] | None = None,
    added_to_file: dict[str, str] | None = None,
) -> str:
    """Render a single hunk, replacing moved sub-blocks >= MIN_BLOCK_LINES.

    Within each same-sign run (+/-), the block is split at non-moved significant
    lines. Each resulting segment is suppressed if all its significant lines are
    moved and it meets MIN_BLOCK_LINES. This handles both the removal side
    (lines deleted from an existing file) and the addition side (lines added to
    a new file or an existing file).

    Args:
        hunk: Parsed Hunk object to render
        moved_lines: Set of content strings identified as moved
        removed_to_file: Mapping of removed content to source filename
        added_to_file: Mapping of added content to destination filename

    Returns:
        Rendered hunk string with moved blocks suppressed, or empty string
        if the hunk is empty after suppression.
    """
    output: list[str] = [hunk.header]
    lines = hunk.lines
    i = 0
    while i < len(lines):
        line = lines[i]
        # Context lines are emitted as-is
        if line.startswith(" ") or (line and line[0] not in ("+", "-")):
            output.append(line)
            i += 1
            continue

        # Gather consecutive lines with the same sign (+/-)
        sign = line[0]
        block: list[str] = []
        j = i
        while j < len(lines) and lines[j].startswith(sign):
            block.append(lines[j])
            j += 1

        output.extend(_render_block(block, moved_lines, removed_to_file, added_to_file))
        i += len(block)

    # Return empty string if only the header remains (hunk is empty after suppression)
    if output == [hunk.header]:
        return ""
    return "\n".join(output)


def render_file_diff(
    file_diff: FileDiff,
    moved_lines: set[str],
    removed_to_file: dict[str, str] | None = None,
    added_to_file: dict[str, str] | None = None,
) -> str:
    """Render all hunks for one file; skip file entirely if all hunks are empty.

    After moved-block suppression.

    Args:
        file_diff: Parsed FileDiff object containing headers and hunks
        moved_lines: Set of content strings identified as moved
        removed_to_file: Mapping of removed content to source filename
        added_to_file: Mapping of added content to destination filename

    Returns:
        Rendered file diff string with headers and non-empty hunks, or empty
        string if all hunks were suppressed.
    """
    rendered_hunks: list[str] = []
    for hunk in file_diff.hunks:
        rendered = render_hunk(hunk, moved_lines, removed_to_file, added_to_file)
        if rendered:
            rendered_hunks.append(rendered)

    if not rendered_hunks:
        if not file_diff.hunks:
            return "\n".join(file_diff.headers)
        return ""

    parts = file_diff.headers + rendered_hunks
    return "\n".join(parts)


def render_compact_diff(plain_diff: str, ansi_diff: str) -> str:
    """Top-level entry point.

    Combine Pass 1 (ANSI) and Pass 2 (Python) moved-line sets, then render.

    Args:
        plain_diff: Plain unified diff string (no ANSI codes)
        ansi_diff: Same diff with ANSI colour codes from git --color-moved

    Returns:
        Compact diff string with moved blocks suppressed, or empty string
        if the input is blank.
    """
    if not plain_diff.strip():
        return ""

    plain_files = parse_diff(plain_diff)
    ansi_moved = extract_moved_blocks_ansi(ansi_diff)  # Pass 1
    py_moved = find_moved_lines(plain_files)  # Pass 2
    all_moved = ansi_moved | py_moved
    removed_to_file, added_to_file = collect_line_sources(
        plain_files
    )  # for annotations

    output: list[str] = []
    for file_diff in plain_files:
        rendered = render_file_diff(
            file_diff, all_moved, removed_to_file, added_to_file
        )
        if rendered:
            output.append(rendered)

    return "\n".join(output)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def get_compact_diff(
    project_dir: Path,
    base_branch: str,
    exclude_paths: list[str] | None = None,
) -> str:
    """Obtain a compact diff by running get_branch_diff() twice and rendering.

    Args:
        project_dir: Path to the project directory containing git repository
        base_branch: Branch to compare against
        exclude_paths: Optional list of paths to exclude from the diff

    Returns:
        Compact diff string with moved blocks suppressed, or empty string
        if there are no changes.
    """
    logger.debug(
        "Getting compact diff for %s (base: %s, excludes: %s)",
        project_dir,
        base_branch,
        exclude_paths,
    )

    plain_diff = get_branch_diff(
        project_dir=project_dir,
        base_branch=base_branch,
        exclude_paths=exclude_paths,
        ansi=False,
    )
    if not plain_diff:
        return ""

    ansi_diff = get_branch_diff(
        project_dir=project_dir,
        base_branch=base_branch,
        exclude_paths=exclude_paths,
        ansi=True,
    )

    return render_compact_diff(plain_diff, ansi_diff)
