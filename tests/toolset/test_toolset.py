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


def test_move_group_spec(tmp_path: Path) -> None:
    """move_file is exported as a writing spec."""
    specs = {s.name: s for s in tool_specs(tmp_path)}

    assert "move_file" in specs
    assert specs["move_file"].group == "workspace.move"
    assert specs["move_file"].read_only is False


@pytest.mark.parametrize(
    ("name", "is_async"),
    [
        ("get_reference_projects", False),
        ("read_reference_file", True),
        ("list_reference_directory", True),
        ("search_reference_files", True),
    ],
)
def test_reference_group_specs(tmp_path: Path, name: str, is_async: bool) -> None:
    """The workspace.reference tools are exported as read-only specs."""
    specs = {s.name: s for s in tool_specs(tmp_path)}

    assert name in specs
    assert specs[name].group == "workspace.reference"
    assert specs[name].read_only is True
    assert inspect.iscoroutinefunction(specs[name].fn) is is_async


def test_git_group_spec(tmp_path: Path) -> None:
    """git is exported as a read-only coroutine spec."""
    specs = {s.name: s for s in tool_specs(tmp_path)}

    assert "git" in specs
    assert specs["git"].group == "workspace.git"
    assert specs["git"].read_only is True
    assert inspect.iscoroutinefunction(specs["git"].fn)


@pytest.mark.parametrize(
    "name",
    [
        "github_issue_view",
        "github_issue_list",
        "github_pr_view",
        "github_search",
        "github_label_list",
        "github_subissue_list",
    ],
)
def test_github_read_group_specs(tmp_path: Path, name: str) -> None:
    """The read-only workspace.github tools are exported as read-only specs."""
    specs = {s.name: s for s in tool_specs(tmp_path)}

    assert name in specs
    assert specs[name].group == "workspace.github"
    assert specs[name].read_only is True


@pytest.mark.parametrize(
    "name",
    [
        "github_issue_create",
        "github_issue_edit",
        "github_issue_set_status",
        "github_issue_comment",
        "github_review_comment_reply",
        "github_review_thread_resolve",
        "github_subissue_add",
        "github_subissue_remove",
        "github_pr_create",
    ],
)
def test_github_write_group_specs(tmp_path: Path, name: str) -> None:
    """The writing workspace.github tools are exported as writing specs."""
    specs = {s.name: s for s in tool_specs(tmp_path)}

    assert name in specs
    assert specs[name].group == "workspace.github"
    assert specs[name].read_only is False


@pytest.mark.parametrize(
    ("name", "is_async"),
    [
        ("check_file_size", False),
        ("check_branch_status", True),
        ("get_base_branch", False),
    ],
)
def test_checks_group_specs(tmp_path: Path, name: str, is_async: bool) -> None:
    """The workspace.checks tools are exported as read-only specs."""
    specs = {s.name: s for s in tool_specs(tmp_path)}

    assert name in specs
    assert specs[name].group == "workspace.checks"
    assert specs[name].read_only is True
    assert inspect.iscoroutinefunction(specs[name].fn) is is_async


def test_edit_file_spec_is_async(tmp_path: Path) -> None:
    """edit_file stays a coroutine function."""
    specs = {s.name: s for s in tool_specs(tmp_path)}

    assert inspect.iscoroutinefunction(specs["edit_file"].fn)
