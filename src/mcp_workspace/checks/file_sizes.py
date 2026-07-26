"""File size check — flags files exceeding a line-count threshold."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set

from mcp_workspace.file_tools.directory_utils import list_files

logger = logging.getLogger(__name__)


@dataclass
class FileMetrics:
    """Metrics for a single file."""

    path: Path
    line_count: int


@dataclass
class CheckResult:
    """Result of file size check."""

    passed: bool
    violations: List[FileMetrics] = field(default_factory=list)
    total_files_checked: int = 0
    allowlisted_count: int = 0
    stale_entries: List[str] = field(default_factory=list)


def count_lines(file_path: Path) -> int:
    """Count lines in a file.

    Returns:
        Number of lines, or -1 for binary/non-UTF-8 files.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except (UnicodeDecodeError, OSError):
        return -1


def load_allowlist(allowlist_path: Path) -> Set[str]:
    """Load allowlist from file.

    Returns:
        Set of normalized (forward-slash) path strings.
    """
    if not allowlist_path.is_file():
        return set()

    entries: Set[str] = set()
    try:
        with open(allowlist_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                # Skip empty lines and comments
                if not stripped or stripped.startswith("#"):
                    continue
                # Strip inline comments
                if "#" in stripped:
                    stripped = stripped[: stripped.index("#")].strip()
                # Normalize to forward slashes
                entries.add(stripped.replace("\\", "/"))
    except OSError as exc:
        logger.warning("Could not read allowlist %s: %s", allowlist_path, exc)

    return entries


def get_file_metrics(files: List[Path], project_dir: Path) -> List[FileMetrics]:
    """Get file metrics for a list of files.

    Returns:
        List of FileMetrics for readable (non-binary) files.
    """
    metrics: List[FileMetrics] = []
    for file_path in files:
        abs_path = project_dir / file_path
        line_count = count_lines(abs_path)
        if line_count >= 0:
            metrics.append(FileMetrics(path=file_path, line_count=line_count))
    return metrics


def check_file_sizes(
    project_dir: Path,
    max_lines: int,
    allowlist: Set[str],
) -> CheckResult:
    """Check file sizes against maximum line limit.

    Args:
        project_dir: Root directory of the project.
        max_lines: Maximum allowed lines per file.
        allowlist: Set of relative paths that are allowed to exceed the limit.

    Returns:
        CheckResult dataclass with pass/fail, violations, and stats.
    """
    # Get all project files
    raw_files = list_files(".", project_dir)
    files = [Path(f) for f in raw_files]

    # Get metrics
    metrics = get_file_metrics(files, project_dir)

    violations: List[FileMetrics] = []
    allowlisted_count = 0
    over_limit_allowlisted: Set[str] = set()

    for m in metrics:
        normalized = str(m.path).replace("\\", "/")
        if m.line_count <= max_lines:
            continue

        if normalized in allowlist:
            allowlisted_count += 1
            over_limit_allowlisted.add(normalized)
        else:
            violations.append(m)

    # Detect stale entries: in allowlist but file doesn't exist or is under limit
    stale_entries: List[str] = []
    for entry in sorted(allowlist):
        if entry in over_limit_allowlisted:
            continue
        # Either file doesn't exist or is under the limit
        stale_entries.append(entry)

    # Sort violations by line_count descending
    violations.sort(key=lambda m: m.line_count, reverse=True)

    return CheckResult(
        passed=len(violations) == 0,
        violations=violations,
        total_files_checked=len(metrics),
        allowlisted_count=allowlisted_count,
        stale_entries=stale_entries,
    )


def render_output(result: CheckResult, max_lines: int) -> str:
    """Render check result for terminal output.

    Returns:
        Multi-line report string describing the check outcome.
    """
    lines: List[str] = []

    if result.passed:
        lines.append(
            f"File size check passed: all {result.total_files_checked} "
            f"files are within {max_lines} lines"
        )
    else:
        count = len(result.violations)
        lines.append(
            f"File size check failed: {count} file(s) exceed {max_lines} lines"
        )
        lines.append("")
        lines.append("Violations:")
        for v in result.violations:
            display_path = str(v.path).replace("\\", "/")
            lines.append(f"  - {display_path}: {v.line_count} lines")
        lines.append("")
        lines.append(
            "Consider refactoring these files or adding them to the allowlist."
        )

    if result.allowlisted_count > 0:
        lines.append(f"\nAllowlisted files: {result.allowlisted_count}")

    if result.stale_entries:
        lines.append(f"\nStale allowlist entries ({len(result.stale_entries)}):")
        for entry in result.stale_entries:
            lines.append(f"  - {entry}")

    return "\n".join(lines)


def render_allowlist(violations: List[FileMetrics]) -> str:
    """Render violations as allowlist entries.

    Returns:
        Newline-separated normalized paths, one per violation.
    """
    return "\n".join(str(v.path).replace("\\", "/") for v in violations)
