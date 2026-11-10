"""Tests for the exported workspace toolset."""

import inspect
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


@pytest.mark.parametrize("name", ["save_file", "edit_file", "append_file"])
def test_write_group_specs(tmp_path: Path, name: str) -> None:
    """The workspace.write tools are exported as writing specs."""
    specs = {s.name: s for s in tool_specs(tmp_path)}

    assert name in specs
    assert specs[name].group == "workspace.write"
    assert specs[name].read_only is False


@pytest.mark.parametrize("name", ["delete_this_file", "delete_directory"])
def test_delete_group_specs(tmp_path: Path, name: str) -> None:
    """The workspace.delete tools are exported as writing specs."""
    specs = {s.name: s for s in tool_specs(tmp_path)}

    assert name in specs
    assert specs[name].group == "workspace.delete"
    assert specs[name].read_only is False


def test_edit_file_spec_is_async(tmp_path: Path) -> None:
    """edit_file stays a coroutine function."""
    specs = {s.name: s for s in tool_specs(tmp_path)}

    assert inspect.iscoroutinefunction(specs["edit_file"].fn)
