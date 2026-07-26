"""File search utilities for glob matching and content searching."""

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pathspec import PathSpec

from mcp_workspace.file_tools.directory_utils import list_files
from mcp_workspace.file_tools.path_utils import normalize_path

_MAX_LINE_CHARS = 500


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
                        + f" ... [truncated, line has {len(stripped)} chars]"
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
        glob: Glob pattern (gitignore semantics). Examples:
            ``*.py`` (any .py at any depth), ``tests/**/test_*.py``,
            ``/README.md`` (root only).
        pattern: Python regex to match file contents. Invalid regex patterns
            are automatically treated as literal text.
            (e.g. "def foo", "TODO.*fix")
        context_lines: Number of context lines around matches.
        max_results: Maximum number of results to return.
        max_result_lines: Maximum total lines in result output.

    Returns:
        Dictionary with search results.

    Raises:
        ValueError: If neither glob nor pattern is provided.
    """
    if glob is None and pattern is None:
        raise ValueError("At least one of 'glob' or 'pattern' must be provided")

    all_files = list_files(".", project_dir=project_dir, use_gitignore=True)

    if glob is not None:
        win32 = sys.platform == "win32"
        norm_glob = glob.lower() if win32 else glob
        spec = PathSpec.from_lines("gitwildmatch", [norm_glob])

        def _norm(p: str) -> str:
            slashed = p.replace("\\", "/")
            return slashed.lower() if win32 else slashed

        matched = [f for f in all_files if spec.match_file(_norm(f))]
    else:
        matched = all_files

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

        return result

    # File search mode: glob only
    total = len(matched)
    truncated = total > max_results

    return {
        "mode": "file_search",
        "files": matched[:max_results],
        "total_files": total,
        "truncated": truncated,
    }
