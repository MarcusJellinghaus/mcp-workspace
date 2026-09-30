"""Cross-tool invariant: every project-relative path emitted uses forward slashes.

This is the single home for *separator* assertions across the guarded tool set.
Per-tool suites assert correctness claims this file cannot express — exact string
values, nested paths, and each path appearing exactly once.
"""

import asyncio
from pathlib import Path
from typing import Any, Callable, Iterator, List, Tuple
from unittest.mock import AsyncMock, patch

import pytest

from mcp_workspace import server, server_reference_tools
from mcp_workspace.file_tools import file_operations
from mcp_workspace.reference_projects import ReferenceProject

_REFERENCE_NAME = "invariant_ref"

# Signature shared by every guarded call: (project, reference_name). The six
# non-reference tools ignore the second argument.
ToolCall = Callable[[Path, str], Any]


def _paths(value: Any, keys: Tuple[str, ...]) -> List[str]:
    """Collect the path-carrying strings from a tool return value.

    For list/str results, every string. For dict results, only the values under
    `keys` (recursively), so match text and other free-form strings are skipped.

    Returns:
        The path-carrying strings found in value.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        collected: List[str] = []
        for item in value:
            collected.extend(_paths(item, keys))
        return collected
    if isinstance(value, dict):
        collected = []
        for key, item in value.items():
            if key in keys:
                collected.extend(_paths(item, keys))
        return collected
    return []


@pytest.fixture
def invariant_project(tmp_path: Path) -> Iterator[Path]:
    """Temp project with nested targets for every guarded tool.

    All file contents are ASCII and backslash-free, so a stray content string
    cannot produce a false failure. Sets the server's project dir — the MCP
    tools read that module global — and restores it on teardown.
    """
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "c.txt").write_text("listed\n", encoding="utf-8")
    (tmp_path / "edit" / "nested").mkdir(parents=True)
    (tmp_path / "edit" / "nested" / "target.txt").write_text(
        "before\n", encoding="utf-8"
    )
    (tmp_path / "move" / "nested").mkdir(parents=True)
    (tmp_path / "move" / "nested" / "source.txt").write_text(
        "moved\n", encoding="utf-8"
    )
    (tmp_path / "doomed" / "nested").mkdir(parents=True)
    (tmp_path / "doomed" / "nested" / "gone.txt").write_text(
        "deleted\n", encoding="utf-8"
    )
    # A non-existent nested entry, so check_file_size also reports a stale line.
    (tmp_path / ".large-files-allowlist").write_text(
        "stale/nested/entry.txt\n", encoding="utf-8"
    )

    previous = server._project_dir
    server.set_project_dir(tmp_path)
    yield tmp_path
    server._project_dir = previous


@pytest.fixture
def reference_project(invariant_project: Path) -> Iterator[str]:
    """Register invariant_project as a reference project; yield its name."""
    previous = server_reference_tools._reference_projects
    server_reference_tools._reference_projects = {
        _REFERENCE_NAME: ReferenceProject(name=_REFERENCE_NAME, path=invariant_project)
    }
    with patch(
        "mcp_workspace.server_reference_tools.ensure_available",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield _REFERENCE_NAME
    server_reference_tools._reference_projects = previous


def _call_list_directory(project: Path, reference_name: str) -> Any:
    """Scoped listing — the shape the reported bug corrupted.

    Returns:
        The raw list_directory result.
    """
    return server.list_directory(path="a")


def _call_search_files(project: Path, reference_name: str) -> Any:
    """File-search mode only, so no match text reaches the assertion.

    Returns:
        The raw search_files result.
    """
    return server.search_files(glob="**/*.txt")


def _call_list_reference_directory(project: Path, reference_name: str) -> Any:
    """Returns:
    The raw list_reference_directory result.
    """
    return asyncio.run(server_reference_tools.list_reference_directory(reference_name))


def _call_search_reference_files(project: Path, reference_name: str) -> Any:
    """File-search mode only, so no match text reaches the assertion.

    Returns:
        The raw search_reference_files result.
    """
    return asyncio.run(
        server_reference_tools.search_reference_files(reference_name, glob="**/*.txt")
    )


def _call_delete_directory(project: Path, reference_name: str) -> Any:
    """Returns:
    The util's list of deleted paths.
    """
    return file_operations.delete_directory("doomed", project, recursive=True)


def _call_move_file(project: Path, reference_name: str) -> Any:
    """Covered at the util layer: the MCP tool returns bool and carries no path.

    Returns:
        The util's result dict, carrying `source` and `destination`.
    """
    return file_operations.move_file(
        "move/nested/source.txt", "move/other/dest.txt", project
    )


def _call_edit_file(project: Path, reference_name: str) -> Any:
    """Narrowed to the diff header lines — the only paths edit_file emits.

    Returns:
        The `---`/`+++` lines of the returned diff.
    """
    diff = asyncio.run(server.edit_file("edit/nested/target.txt", "before", "after"))
    return [
        line
        for line in diff.splitlines()
        if line.startswith("---") or line.startswith("+++")
    ]


def _call_check_file_size(project: Path, reference_name: str) -> Any:
    """Narrowed to the violation and stale-allowlist lines.

    max_lines=0 guarantees the nested fixture files violate, so the report
    actually carries paths.

    Returns:
        The `  - ` lines of the returned report.
    """
    report = server.check_file_size(max_lines=0)
    return [line for line in report.splitlines() if line.startswith("  - ")]


# Adding a tool to the guarded set is one line here.
#
# Excluded deliberately: git, github_pr_view and check_branch_status. Their
# paths arrive from the GitHub API already forward-slashed, so nothing here can
# regress them and including them would mean mocking the API for no added guard.
GUARDED_TOOLS: List[Tuple[str, ToolCall, Tuple[str, ...]]] = [
    ("list_directory", _call_list_directory, ()),
    ("search_files", _call_search_files, ("files", "skipped_files")),
    ("list_reference_directory", _call_list_reference_directory, ()),
    (
        "search_reference_files",
        _call_search_reference_files,
        ("files", "skipped_files"),
    ),
    ("delete_directory", _call_delete_directory, ()),
    ("move_file", _call_move_file, ("source", "destination")),
    ("edit_file", _call_edit_file, ()),
    ("check_file_size", _call_check_file_size, ()),
]


@pytest.mark.parametrize(
    "tool_name, call, path_keys", GUARDED_TOOLS, ids=[t[0] for t in GUARDED_TOOLS]
)
def test_emitted_paths_use_forward_slashes(
    tool_name: str,
    call: ToolCall,
    path_keys: Tuple[str, ...],
    invariant_project: Path,
    reference_project: str,
) -> None:
    """No path any guarded tool emits contains a native separator."""
    result = call(invariant_project, reference_project)

    emitted = _paths(result, path_keys)
    assert emitted, f"{tool_name} emitted no paths, so the assertion is vacuous"
    for path in emitted:
        assert "\\" not in path, f"{tool_name} emitted a native separator: {path!r}"


def test_paths_collects_from_list_result() -> None:
    """The assertion can fail: a backslashed string in a list result is collected."""
    assert _paths(["a\\b.txt"], ()) == ["a\\b.txt"]


def test_paths_collects_from_named_dict_key() -> None:
    """The assertion can fail: a backslashed string under a named key is collected."""
    result = {"files": ["a\\b.txt"], "matches": ["text\\not\\a\\path"]}

    assert _paths(result, ("files",)) == ["a\\b.txt"]
