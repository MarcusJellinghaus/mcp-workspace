"""Guard tests: MCP tool descriptions document glob semantics.

The `glob` argument uses gitignore/wildmatch semantics, which surprise callers
who expect shell globbing. The descriptions have drifted once already, so the
key phrases are pinned here.
"""

from typing import Any

import pytest

from mcp_workspace import server, server_reference_tools

GLOB_DOC_PHRASES = [
    "gitignore",
    "brace expansion is not supported",
    "any depth",
    "case-insensitive",
    "git ls-files",
    "glob_note",
]


@pytest.mark.parametrize("phrase", GLOB_DOC_PHRASES)
@pytest.mark.parametrize(
    "func",
    [server.search_files, server_reference_tools.search_reference_files],
    ids=["search_files", "search_reference_files"],
)
def test_tool_description_documents_glob_semantics(func: Any, phrase: str) -> None:
    assert phrase in (func.__doc__ or "").lower()
