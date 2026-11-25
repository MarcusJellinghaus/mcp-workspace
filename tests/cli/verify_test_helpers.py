"""Rendering helpers for the verify formatter tests.

Expected text uses hardcoded columns: the default label width is 22, so the
value column is 32 (2 indent + 22 label + 1 + 6 marker slot + 1).
"""

import re
from collections.abc import Sequence

from mcp_coder_utils.verify_render import Line, render_rows

SYMBOLS: dict[str, str] = {"success": "[OK]", "failure": "[ERR]", "warning": "[WARN]"}
DEFAULT_LABEL_WIDTH = 22
VALUE_COL = 32
MARKER_RE = re.compile("|".join(re.escape(s) for s in SYMBOLS.values()))


def render(lines: Sequence[Line]) -> str:
    """Render a section's lines to text."""
    return "\n".join(render_rows(lines))


def row(
    label: str,
    marker: str,
    value: str,
    *,
    indent: int = 2,
    label_width: int = DEFAULT_LABEL_WIDTH,
) -> str:
    """Expected text of one rendered row, built from hardcoded column widths."""
    field = label_width - (indent - 2)
    return f"{' ' * indent}{label.ljust(field)} {marker.ljust(6)} {value}".rstrip()


def has_row(output: str, label: str, marker: str, value: str) -> bool:
    """True if the indent-4 row for *label* carries *marker* and ends in *value*."""
    return any(
        line.startswith(f"    {label} ") and marker in line and line.endswith(value)
        for line in output.splitlines()
    )


def assert_value_at_column(line: str, col: int) -> None:
    """Assert the value of ``line`` starts exactly at ``col``."""
    assert col < len(line), f"line shorter than value column {col}: {line!r}"
    assert line[col - 1].isspace(), f"prefix overflowed past col {col - 1}: {line!r}"
    assert not line[col].isspace(), f"value missing at col {col}: {line!r}"


def assert_section_aligned(text: str) -> int:
    """All marker-bearing rows share marker and value columns; return row count."""
    first: tuple[int, int] | None = None
    count = 0
    for line in text.splitlines():
        m = MARKER_RE.search(line)
        rest = line[m.end() :] if m else ""
        if m is None or not rest.strip():
            continue
        value_col = len(line) - len(rest.lstrip())
        if first is None:
            first = (m.start(), value_col)
        assert m.start() == first[0], f"marker at col {m.start()}: {line!r}"
        assert_value_at_column(line, first[1])
        count += 1
    return count
