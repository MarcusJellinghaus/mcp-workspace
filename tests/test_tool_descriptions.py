"""Guard tests: MCP tool descriptions document glob semantics.

The `glob` argument uses gitignore/wildmatch semantics, which surprise callers
who expect shell globbing. The descriptions have drifted once already, so the
key phrases are pinned here.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from mcp_workspace import server_reference_tools
from mcp_workspace.toolset import tool_specs

GLOB_DOC_PHRASES = [
    "gitignore",
    "brace expansion is not supported",
    "any depth",
    "case-insensitive",
    "git ls-files",
    "glob_note",
]


def _search_files_text(project_dir: Path) -> str:
    """Return the search_files description plus its glob field description."""
    spec = next(s for s in tool_specs(project_dir) if s.name == "search_files")
    glob_doc = spec.args_model.model_json_schema()["properties"]["glob"]["description"]
    return f"{spec.description}\n{glob_doc}"


def _search_reference_files_text(project_dir: Path) -> str:
    """Return the search_reference_files docstring."""
    return server_reference_tools.search_reference_files.__doc__ or ""


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
