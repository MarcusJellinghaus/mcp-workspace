"""Guard tests: output shape of the dict-returning MCP tools.

FastMCP's `func_metadata` is annotation-sensitive: `dict[str, Any]` returns the
dict as structured output, while `typing.Dict[str, Any]` wraps it in
`{"result": ...}`. Respelling an annotation changes what clients receive, so the
unwrapped shape is pinned here.
"""

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_workspace import server_reference_tools
from mcp_workspace.server import mcp

DICT_RETURNING_TOOLS = [
    "search_files",
    "search_reference_files",
    "get_reference_projects",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", DICT_RETURNING_TOOLS)
async def test_output_schema_is_unwrapped(tool_name: str) -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    schema = tools[tool_name].outputSchema

    assert schema is not None
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is True
    assert "result" not in schema.get("properties", {})


@pytest.mark.asyncio
async def test_structured_content_is_unwrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_reference_tools, "_reference_projects", {})

    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool("get_reference_projects", {})

    assert not result.isError
    assert result.structuredContent is not None
    assert "result" not in result.structuredContent
    assert set(result.structuredContent) == {"count", "projects", "usage"}
