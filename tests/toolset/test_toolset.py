"""Tests for the exported workspace toolset."""

from pathlib import Path

import pytest

from mcp_workspace.toolset import tool_specs


@pytest.mark.parametrize("name", ["read_file", "list_directory", "search_files"])
def test_read_group_specs(tmp_path: Path, name: str) -> None:
    """The workspace.read tools are exported as read-only specs."""
    specs = {s.name: s for s in tool_specs(tmp_path)}

    assert name in specs
    assert specs[name].group == "workspace.read"
    assert specs[name].read_only is True
