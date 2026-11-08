"""Refusals reach an MCP client as tool errors, without protected content."""

from pathlib import Path
from typing import Any

import pytest
from git import Repo
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextContent

from mcp_workspace import server, server_reference_tools
from mcp_workspace.reference_projects import ReferenceProject

SECRET_TEXT = "SECRET-VALUE"
OUTSIDE_TEXT = "OUTSIDE-VALUE"
CONFIG_MARKER = "repositoryformatversion"

pytestmark = pytest.mark.git_integration


def _text(result: CallToolResult) -> str:
    return "\n".join(
        block.text for block in result.content if isinstance(block, TextContent)
    )


async def _call(tool: str, arguments: dict[str, Any]) -> CallToolResult:
    """Call a tool through a client session connected to the real server object."""
    async with create_connected_server_and_client_session(server.mcp) as session:
        return await session.call_tool(tool, arguments)


def _make_repo(path: Path) -> Repo:
    """Create a repository with a gitignored secret and a second branch."""
    path.mkdir()
    repo = Repo.init(path)
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "test@example.com")
        config.set_value("commit", "gpgsign", "false")
    (path / ".gitignore").write_text(".env\n", encoding="utf-8")
    (path / "plain.txt").write_text("plain\n", encoding="utf-8")
    repo.index.add([".gitignore", "plain.txt"])
    repo.index.commit("first")
    repo.git.branch("-M", "main")
    repo.git.branch("victim")
    (path / ".env").write_text(SECRET_TEXT + "\n", encoding="utf-8")
    return repo


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    """Workspace and reference repositories, plus a file outside both."""
    repo = _make_repo(tmp_path / "workspace")
    _make_repo(tmp_path / "ref")
    (tmp_path / "outside.txt").write_text(OUTSIDE_TEXT + "\n", encoding="utf-8")
    (tmp_path / "outside2.txt").write_text(OUTSIDE_TEXT + "2\n", encoding="utf-8")
    monkeypatch.setattr(server, "_project_dir", tmp_path / "workspace")
    monkeypatch.setattr(
        server_reference_tools,
        "_reference_projects",
        {"ref": ReferenceProject(name="ref", path=tmp_path / "ref")},
    )
    return repo


async def _assert_git_refusals(
    tmp_path: Path, extra: dict[str, Any], repo: Repo
) -> None:
    outside = str(tmp_path / "outside.txt")
    other = str(tmp_path / "outside2.txt")
    refused: list[dict[str, Any]] = [
        {"command": "branch", "args": ["-v", "-vD", "victim"]},
        {"command": "branch", "args": ["-v", "created"]},
        {"command": "diff", "args": [outside, other]},
        {"command": "diff", "args": [outside, ".env"]},
        {"command": "diff", "pathspec": [outside, ".env"]},
        {"command": "show", "args": ["HEAD:../outside.txt"]},
        {"command": "fetch", "args": ["-f", str(tmp_path / "ref"), "+main:main"]},
        {"command": "fetch", "args": ["origin", "main:main"]},
        {"command": "ls_remote", "args": [str(tmp_path / "ref")]},
        {"command": "tag", "args": ["-d", "x"]},
    ]
    heads_before = {head.name: head.commit.hexsha for head in repo.heads}
    for arguments in refused:
        result = await _call("git", {**arguments, **extra})
        assert result.isError, arguments
        assert SECRET_TEXT not in _text(result), arguments
        assert OUTSIDE_TEXT not in _text(result), arguments
    assert {head.name: head.commit.hexsha for head in repo.heads} == heads_before


@pytest.mark.asyncio
async def test_git_refusals_on_workspace(workspace: Repo, tmp_path: Path) -> None:
    await _assert_git_refusals(tmp_path, {}, workspace)


@pytest.mark.asyncio
async def test_git_refusals_on_reference_project(
    workspace: Repo, tmp_path: Path
) -> None:
    await _assert_git_refusals(
        tmp_path, {"reference_name": "ref"}, Repo(tmp_path / "ref")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("read_file", {"file_path": ".git/config"}),
        ("read_file", {"file_path": ".GIT/config"}),
        ("read_file", {"file_path": ".git./config"}),
        ("read_file", {"file_path": ".env"}),
        ("read_file", {"file_path": ".env::$DATA"}),
        ("list_directory", {"path": ".git"}),
        ("save_file", {"file_path": ".GIT/hooks/new-file", "content": "x"}),
        ("append_file", {"file_path": ".GIT/config", "content": "x"}),
        (
            "edit_file",
            {"file_path": ".GIT/config", "old_string": "core", "new_string": "x"},
        ),
        ("delete_this_file", {"file_path": ".GIT/config"}),
        ("delete_directory", {"dir_path": ".GIT", "recursive": True}),
        ("move_file", {"source_path": ".GIT/config", "destination_path": "moved"}),
        ("move_file", {"source_path": "plain.txt", "destination_path": ".GIT/moved"}),
        ("read_reference_file", {"reference_name": "ref", "file_path": ".env"}),
        ("read_reference_file", {"reference_name": "ref", "file_path": ".GIT/config"}),
    ],
)
async def test_file_tool_refusals(
    workspace: Repo, tool: str, arguments: dict[str, Any]
) -> None:
    project = Path(workspace.working_dir)
    config_before = (project / ".git" / "config").read_bytes()
    result = await _call(tool, arguments)
    assert result.isError
    assert SECRET_TEXT not in _text(result)
    assert CONFIG_MARKER not in _text(result)
    assert (project / ".git" / "config").read_bytes() == config_before
    assert (project / "plain.txt").is_file()


@pytest.mark.asyncio
async def test_search_tools_return_no_protected_content(workspace: Repo) -> None:
    pattern = f"{SECRET_TEXT}|{CONFIG_MARKER}"
    for tool, arguments in (
        ("search_files", {"pattern": pattern}),
        ("search_reference_files", {"reference_name": "ref", "pattern": pattern}),
    ):
        result = await _call(tool, arguments)
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["details"] == []


@pytest.mark.asyncio
async def test_git_failure_reaches_client_as_error_text(workspace: Repo) -> None:
    result = await _call("git", {"command": "log", "args": ["no-such-rev"]})
    assert result.isError
    assert "exit code" in _text(result)
    assert "cmdline: git log" in _text(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"command": "log", "args": ["-n1", "--oneline"]}, "first"),
        ({"command": "branch", "args": ["--list"]}, "victim"),
        ({"command": "branch", "args": ["--show-current"]}, "main"),
        ({"command": "rev_parse", "args": ["--abbrev-ref", "HEAD"]}, "main"),
        ({"command": "show", "args": ["HEAD:.gitignore"]}, ".env"),
        ({"command": "check_ignore", "pathspec": [".env"]}, ".env"),
        ({"command": "ls_files"}, "plain.txt"),
    ],
)
async def test_ordinary_git_calls_succeed(
    workspace: Repo, arguments: dict[str, Any], expected: str
) -> None:
    for extra in ({}, {"reference_name": "ref"}):
        result = await _call("git", {**arguments, **extra})
        assert not result.isError, _text(result)
        assert expected in _text(result)
