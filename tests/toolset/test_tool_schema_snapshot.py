"""Guard test: MCP tool input schemas match a fixed snapshot.

The snapshot was captured before the tools moved into the toolset package, so
any schema change caused by the move fails here. `description` and `title`
annotations are stripped; output schemas are covered by
`test_tool_output_schema.py`.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from mcp_workspace.server import create_server

SNAPSHOT_DIR = Path(__file__).with_name("tool_schemas")

_ANNOTATION_KEYS = {"description", "title"}


def _strip(node: Any) -> Any:
    """Drop 'description' and 'title' keys recursively."""
    if isinstance(node, dict):
        stripped: dict[str, Any] = {}
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                # Keys here are parameter names, which may be "title".
                stripped[key] = {name: _strip(schema) for name, schema in value.items()}
            elif key not in _ANNOTATION_KEYS:
                stripped[key] = _strip(value)
        return stripped
    if isinstance(node, list):
        return [_strip(item) for item in node]
    return node


def _snapshot() -> dict[str, Any]:
    """{tool name: stripped inputSchema} from one JSON file per tool."""
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in SNAPSHOT_DIR.glob("*.json")
    }


async def _current_schemas(project_dir: Path) -> dict[str, Any]:
    """{tool name: stripped inputSchema} from a freshly built server."""
    tools = await create_server(project_dir).list_tools()
    return {tool.name: _strip(tool.inputSchema) for tool in tools}


@pytest.mark.asyncio
async def test_tool_schemas_match_snapshot(tmp_path: Path) -> None:
    current = await _current_schemas(tmp_path)
    expected = _snapshot()

    assert sorted(current) == sorted(expected)
    for name in expected:
        assert current[name] == expected[name], name


def test_snapshot_keeps_title_parameter() -> None:
    schema = _snapshot()["github_issue_create"]

    title = schema["properties"]["title"]
    assert title["type"] == "string"
    assert "default" not in title
    assert "title" in schema["required"]
