"""Guard tests: MCP tool descriptions document glob semantics and ref reads.

The `glob` argument uses gitignore/wildmatch semantics, which surprise callers
who expect shell globbing. The reference read tools read `origin/<default>`,
not the working tree. The descriptions have drifted once already, so the
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
    "glob_note",
]

SEARCH_FILES_GLOB_PHRASES = ["git ls-files"]

SEARCH_REFERENCE_FILES_GLOB_PHRASES = [
    "ls_tree",
    "--name-only",
    "origin/main",
    "max_lines",
]

REFERENCE_READ_TOOLS = [
    "read_reference_file",
    "search_reference_files",
    "list_reference_directory",
]

REFERENCE_READ_PHRASES = [
    "origin/",
    "fetched automatically",
    "tracked",
    'git(command="show"',
    "max_lines",
    "-s<text>",
]


def _tool_text(project_dir: Path, name: str) -> str:
    """Return a tool's description plus its glob field description."""
    spec = next(s for s in tool_specs(project_dir) if s.name == name)
    glob_doc = spec.args_model.model_json_schema()["properties"]["glob"]["description"]
    return f"{spec.description}\n{glob_doc}"


def _description(project_dir: Path, name: str) -> str:
    """Return a tool's description, lower-cased."""
    spec = next(s for s in tool_specs(project_dir) if s.name == name)
    return spec.description.lower()


def _field_description(project_dir: Path, name: str, field: str) -> str:
    """Return the description of one of a tool's fields, lower-cased."""
    spec = next(s for s in tool_specs(project_dir) if s.name == name)
    schema = spec.args_model.model_json_schema()
    return str(schema["properties"][field]["description"]).lower()


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


def test_list_reference_directory_description_lists_label(tmp_path: Path) -> None:
    description = _description(tmp_path, "list_reference_directory")
    assert "(not committed)" in description
    assert "strip that suffix" in description


@pytest.mark.parametrize("name", WRITE_TOOLS)
def test_write_tool_description_mentions_file_access(name: str, tmp_path: Path) -> None:
    description = _description(tmp_path, name)
    assert "not exposed read-write by .mcp-file-access" in description
    assert "no write access" in description


@pytest.mark.parametrize("phrase", SEARCH_FILES_GLOB_PHRASES)
def test_search_files_glob_points_to_git_ls_files(phrase: str, tmp_path: Path) -> None:
    assert phrase in _search_files_text(tmp_path).lower()


@pytest.mark.parametrize("phrase", SEARCH_REFERENCE_FILES_GLOB_PHRASES)
def test_search_reference_files_glob_points_to_ls_tree(
    phrase: str, tmp_path: Path
) -> None:
    glob_doc = _field_description(tmp_path, "search_reference_files", "glob")
    assert phrase in glob_doc


def test_search_reference_files_glob_drops_git_ls_files(tmp_path: Path) -> None:
    """git ls-files reads the working tree's index, not the ref being searched."""
    glob_doc = _field_description(tmp_path, "search_reference_files", "glob")
    assert "git ls-files" not in glob_doc


@pytest.mark.parametrize("phrase", REFERENCE_READ_PHRASES)
@pytest.mark.parametrize("tool", REFERENCE_READ_TOOLS)
def test_reference_read_tool_documents_reading_at_ref(
    tool: str, phrase: str, tmp_path: Path
) -> None:
    assert phrase in _description(tmp_path, tool)


@pytest.mark.parametrize(
    "tool, phrase",
    [
        ("list_reference_directory", "last entry may be a note"),
        ("search_reference_files", "freshness"),
    ],
)
def test_reference_read_tool_documents_note_placement(
    tool: str, phrase: str, tmp_path: Path
) -> None:
    assert phrase in _description(tmp_path, tool)


def test_git_reference_name_documents_fetch(tmp_path: Path) -> None:
    assert "fetch" in _field_description(tmp_path, "git", "reference_name")
