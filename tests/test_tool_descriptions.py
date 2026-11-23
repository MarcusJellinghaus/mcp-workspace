"""Guard tests: MCP tool descriptions document glob semantics.

The `glob` argument uses gitignore/wildmatch semantics, which surprise callers
who expect shell globbing. The descriptions have drifted once already, so the
key phrases are pinned here.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from mcp_workspace.toolset import tool_specs

GLOB_DOC_PHRASES = [
    "gitignore",
    "brace expansion is not supported",
    "any depth",
    "case-insensitive",
    "git ls-files",
    "glob_note",
]


def _tool_text(project_dir: Path, name: str) -> str:
    """Return a tool's description plus its glob field description."""
    spec = next(s for s in tool_specs(project_dir) if s.name == name)
    glob_doc = spec.args_model.model_json_schema()["properties"]["glob"]["description"]
    return f"{spec.description}\n{glob_doc}"


def _search_files_text(project_dir: Path) -> str:
    """Return the search_files description plus its glob field description."""
    return _tool_text(project_dir, "search_files")


def _search_reference_files_text(project_dir: Path) -> str:
    """Return the search_reference_files description plus its glob field description."""
    return _tool_text(project_dir, "search_reference_files")


@pytest.mark.parametrize("phrase", GLOB_DOC_PHRASES)
@pytest.mark.parametrize(
    "get_text",
    [_search_files_text, _search_reference_files_text],
    ids=["search_files", "search_reference_files"],
)
def test_tool_description_documents_glob_semantics(
    get_text: Callable[[Path], str], phrase: str, tmp_path: Path
) -> None:
    assert phrase in get_text(tmp_path).lower()


READ_TOOLS = ["read_file", "read_reference_file"]
WRITE_TOOLS = [
    "save_file",
    "append_file",
    "edit_file",
    "delete_this_file",
    "move_file",
    "delete_directory",
]


def _description(project_dir: Path, name: str) -> str:
    """Return a tool's description, lowercased."""
    spec = next(s for s in tool_specs(project_dir) if s.name == name)
    return spec.description.lower()


@pytest.mark.parametrize("name", READ_TOOLS)
def test_read_tool_description_mentions_file_access(name: str, tmp_path: Path) -> None:
    description = _description(tmp_path, name)
    assert ".mcp-file-access" in description
    assert "not exposed by" in description


@pytest.mark.parametrize("name", ["search_files", "search_reference_files"])
def test_search_tool_description_mentions_warning(name: str, tmp_path: Path) -> None:
    description = _description(tmp_path, name)
    assert '"warning" key' in description
    assert ".mcp-file-access" in description


def test_list_directory_description_lists_labels(tmp_path: Path) -> None:
    description = _description(tmp_path, "list_directory")
    assert "(read-only, not committed)" in description
    assert "omitted while" in description


@pytest.mark.parametrize("name", WRITE_TOOLS)
def test_write_tool_description_mentions_file_access(name: str, tmp_path: Path) -> None:
    description = _description(tmp_path, name)
    assert "not exposed read-write by .mcp-file-access" in description
    assert "no write access" in description
