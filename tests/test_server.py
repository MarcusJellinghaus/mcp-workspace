"""Tests for the MCP server API endpoints."""

import logging
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP
from mcp_coder_utils.tool_spec import tool_spec

from mcp_workspace.file_tools import DEFAULT_READ_MAX_LINES
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.server import FastMCPSink, create_server, run_server
from mcp_workspace.toolset._context import WorkspaceContext, check_not_gitignored
from tests.conftest import ToolMap

# Python path is now configured via pytest configuration in pyproject.toml

# Test constants
TEST_DIR = Path("testdata/test_file_tools")
TEST_FILE = TEST_DIR / "test_api_file.txt"
TEST_CONTENT = "This is API test content."


def setup_function() -> None:
    """Setup for each test function."""
    # Ensure the test directory exists
    TEST_DIR.mkdir(parents=True, exist_ok=True)


def teardown_function() -> None:
    """Teardown for each test function."""
    # Clean up any test files
    if TEST_FILE.exists():
        TEST_FILE.unlink()


def test_save_file(project_dir: Path, tools: ToolMap) -> None:
    """Test the save_file tool."""
    result = tools["save_file"](str(TEST_FILE), TEST_CONTENT)

    # Create absolute path for verification
    abs_file_path = project_dir / TEST_FILE

    assert result is True
    assert abs_file_path.exists()

    with open(abs_file_path, encoding="utf-8") as f:
        content = f.read()
    assert content == TEST_CONTENT


def test_read_file(project_dir: Path, tools: ToolMap) -> None:
    """Test the read_file tool."""
    # Create absolute path for test file
    abs_file_path = project_dir / TEST_FILE

    # Create a test file
    with open(abs_file_path, "w", encoding="utf-8") as f:
        f.write(TEST_CONTENT)

    content = tools["read_file"](str(TEST_FILE))

    assert content == TEST_CONTENT


def test_read_file_not_found(tools: ToolMap) -> None:
    """Test the read_file tool with a non-existent file."""
    non_existent_file = TEST_DIR / "non_existent.txt"

    # Ensure the file doesn't exist
    if Path(non_existent_file).exists():
        Path(non_existent_file).unlink()

    with pytest.raises(FileNotFoundError):
        tools["read_file"](str(non_existent_file))


def test_append_file(project_dir: Path, tools: ToolMap) -> None:
    """Test the append_file tool."""
    # Create absolute path for test file
    abs_file_path = project_dir / TEST_FILE

    # Create initial content
    initial_content = "Initial content.\n"
    with open(abs_file_path, "w", encoding="utf-8") as f:
        f.write(initial_content)

    # Append content to the file
    append_content = "Appended content."
    result = tools["append_file"](str(TEST_FILE), append_content)

    # Verify the file was updated
    assert result is True
    assert abs_file_path.exists()

    # Verify the combined content
    expected_content = initial_content + append_content
    with open(abs_file_path, encoding="utf-8") as f:
        content = f.read()
    assert content == expected_content


def test_append_file_empty(project_dir: Path, tools: ToolMap) -> None:
    """Test appending to an empty file."""
    # Create the empty file
    empty_file = TEST_DIR / "empty_file.txt"
    abs_file_path = project_dir / empty_file
    with open(abs_file_path, "w", encoding="utf-8") as f:
        pass  # Create an empty file

    # Append content to the empty file
    append_content = "Content added to empty file."
    result = tools["append_file"](str(empty_file), append_content)

    # Verify the file was updated
    assert result is True
    assert abs_file_path.exists()

    # Verify the content
    with open(abs_file_path, encoding="utf-8") as f:
        content = f.read()
    assert content == append_content


def test_append_file_not_found(tools: ToolMap) -> None:
    """Test appending to a file that doesn't exist."""
    non_existent_file = TEST_DIR / "non_existent_append.txt"

    # Ensure the file doesn't exist
    if Path(non_existent_file).exists():
        Path(non_existent_file).unlink()

    # Test appending to a non-existent file
    with pytest.raises(FileNotFoundError):
        tools["append_file"](str(non_existent_file), "This should fail")


def test_move_file(project_dir: Path, tools: ToolMap) -> None:
    """Test the move_file tool."""
    # Create source file
    source_file = TEST_DIR / "source.txt"
    dest_file = TEST_DIR / "dest.txt"
    abs_source = project_dir / source_file
    abs_dest = project_dir / dest_file

    # Create source file
    abs_source.parent.mkdir(parents=True, exist_ok=True)
    with open(abs_source, "w", encoding="utf-8") as f:
        f.write("Test content")

    # Clean up destination if exists
    if abs_dest.exists():
        abs_dest.unlink()

    # Move the file
    result = tools["move_file"](str(source_file), str(dest_file))

    assert result is True
    assert not abs_source.exists()
    assert abs_dest.exists()
    with open(abs_dest, encoding="utf-8") as f:
        assert f.read() == "Test content"

    # Clean up
    if abs_dest.exists():
        abs_dest.unlink()


def test_move_file_simplified_errors(project_dir: Path, tools: ToolMap) -> None:
    """Test that server endpoint returns simplified error messages."""
    # Test file not found
    with pytest.raises(FileNotFoundError) as exc_info:
        tools["move_file"]("nonexistent.txt", "dest.txt")
    assert str(exc_info.value) == "File not found"  # Simple message

    # Test destination exists
    source_file = TEST_DIR / "source_exists.txt"
    dest_file = TEST_DIR / "existing.txt"
    abs_source = project_dir / source_file
    abs_dest = project_dir / dest_file

    # Create both files
    abs_source.parent.mkdir(parents=True, exist_ok=True)
    with open(abs_source, "w", encoding="utf-8") as f:
        f.write("Source")
    with open(abs_dest, "w", encoding="utf-8") as f:
        f.write("Existing")

    with pytest.raises(FileExistsError) as exc_info2:
        tools["move_file"](str(source_file), str(dest_file))
    assert str(exc_info2.value) == "Destination already exists"  # Simple message

    # Clean up
    if abs_source.exists():
        abs_source.unlink()
    if abs_dest.exists():
        abs_dest.unlink()


@patch("mcp_workspace.toolset.move.move_file_util")
def test_move_file_permission_error(mock_move: MagicMock, tools: ToolMap) -> None:
    """Test permission error handling in move_file."""
    # Mock move_file_util to raise PermissionError
    mock_move.side_effect = PermissionError("Access denied to file: /some/path")

    with pytest.raises(PermissionError) as exc:
        tools["move_file"]("readonly.txt", "dest.txt")
    assert str(exc.value) == "Permission denied"  # Simple message


@patch("mcp_workspace.toolset.move.move_file_util")
def test_move_file_security_error(mock_move: MagicMock, tools: ToolMap) -> None:
    """Test security error handling in move_file."""
    # Mock move_file_util to raise ValueError with security message
    mock_move.side_effect = ValueError("Security: Path outside project directory")

    with pytest.raises(ValueError) as exc:
        tools["move_file"]("../outside.txt", "dest.txt")
    assert str(exc.value) == "Invalid path"  # Simple message


@patch("mcp_workspace.toolset.move.move_file_util")
def test_move_file_generic_error(mock_move: MagicMock, tools: ToolMap) -> None:
    """Test generic error handling in move_file."""
    # Mock move_file_util to raise a generic exception
    mock_move.side_effect = RuntimeError("Some complex internal error")

    with pytest.raises(RuntimeError) as exc:
        tools["move_file"]("source.txt", "dest.txt")
    assert str(exc.value) == "Move operation failed"  # Simple message


# --- Gitignore enforcement tests ---


@pytest.fixture
def gitignore_project(project_dir: Path) -> Path:
    """Project dir with a .gitignore that blocks *.log and __pycache__/."""
    (project_dir / ".gitignore").write_text("*.log\n__pycache__/\n")
    return project_dir


def test_read_file_gitignored(gitignore_project: Path, tools: ToolMap) -> None:
    """read_file on gitignored file raises ValueError."""
    (gitignore_project / "debug.log").write_text("log content")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        tools["read_file"]("debug.log")


def test_save_file_gitignored(gitignore_project: Path, tools: ToolMap) -> None:
    """save_file to gitignored path raises ValueError."""
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        tools["save_file"]("output.log", "content")


@pytest.mark.asyncio
async def test_edit_file_gitignored(gitignore_project: Path, tools: ToolMap) -> None:
    """edit_file on gitignored file raises ValueError."""
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        await tools["edit_file"]("debug.log", old_string="a", new_string="b")


def test_append_file_gitignored(gitignore_project: Path, tools: ToolMap) -> None:
    """append_file to gitignored file raises ValueError."""
    (gitignore_project / "debug.log").write_text("existing")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        tools["append_file"]("debug.log", "more")


def test_delete_file_gitignored(gitignore_project: Path, tools: ToolMap) -> None:
    """delete_this_file on gitignored file raises ValueError."""
    (gitignore_project / "debug.log").write_text("to delete")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        tools["delete_this_file"]("debug.log")


def test_delete_directory_gitignored(gitignore_project: Path, tools: ToolMap) -> None:
    """delete_directory on a gitignored top-level dir raises ValueError."""
    cache_dir = gitignore_project / "__pycache__"
    cache_dir.mkdir()
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        tools["delete_directory"]("__pycache__")


def test_delete_directory_recursive_deletes_gitignored_children(
    gitignore_project: Path, tools: ToolMap
) -> None:
    """Recursive delete removes a tree including gitignored children."""
    build_dir = gitignore_project / "build"
    nested_cache = build_dir / "__pycache__"
    nested_cache.mkdir(parents=True)
    (nested_cache / "x.pyc").write_text("bytecode")
    tools["delete_directory"]("build", recursive=True)
    assert not build_dir.exists()


def test_move_file_gitignored_source(gitignore_project: Path, tools: ToolMap) -> None:
    """move_file with gitignored source raises ValueError."""
    (gitignore_project / "debug.log").write_text("content")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        tools["move_file"]("debug.log", "renamed.txt")


def test_move_file_gitignored_destination(
    gitignore_project: Path, tools: ToolMap
) -> None:
    """move_file with gitignored destination raises ValueError."""
    (gitignore_project / "safe.txt").write_text("content")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        tools["move_file"]("safe.txt", "output.log")


def test_read_file_in_gitignored_directory(
    gitignore_project: Path, tools: ToolMap
) -> None:
    """File inside gitignored directory (__pycache__/) is blocked."""
    cache_dir = gitignore_project / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "module.pyc").write_text("bytecode")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        tools["read_file"]("__pycache__/module.pyc")


def test_read_file_git_config(gitignore_project: Path, tools: ToolMap) -> None:
    """read_file on .git/config is blocked."""
    git_dir = gitignore_project / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        tools["read_file"](".git/config")


def test_save_file_git_hooks(gitignore_project: Path, tools: ToolMap) -> None:
    """save_file to .git/hooks/ is blocked."""
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        tools["save_file"](".git/hooks/pre-commit", "#!/bin/sh")


def test_read_file_not_gitignored(gitignore_project: Path, tools: ToolMap) -> None:
    """Non-gitignored file works normally."""
    (gitignore_project / "readme.txt").write_text("hello")
    content = tools["read_file"]("readme.txt")
    assert content == "hello"


def test_save_file_not_gitignored(gitignore_project: Path, tools: ToolMap) -> None:
    """Non-gitignored save works normally."""
    result = tools["save_file"]("readme.txt", "hello")
    assert result is True


def test_check_not_gitignored_absolute_path_message_is_forward_slash(
    gitignore_project: Path,
) -> None:
    """An absolute gitignored path is reported project-relative with '/'."""
    nested = gitignore_project / "sub" / "deeper"
    nested.mkdir(parents=True)
    (nested / "debug.log").write_text("log content")
    ctx = WorkspaceContext(gitignore_project, {}, None, None, False, True)

    with pytest.raises(ValueError) as excinfo:
        check_not_gitignored(ctx, str(nested / "debug.log"))

    assert "File 'sub/deeper/debug.log' is excluded by .gitignore" in str(excinfo.value)


def test_read_file_no_gitignore(project_dir: Path, tools: ToolMap) -> None:
    """Without .gitignore, all files are accessible."""
    (project_dir / "debug.log").write_text("log content")
    content = tools["read_file"]("debug.log")
    assert content == "log content"


@patch("mcp_workspace.toolset.read.read_file_util")
def test_read_file_forwards_line_range_params(
    mock_read_file_util: MagicMock, project_dir: Path, tools: ToolMap
) -> None:
    """Test that read_file forwards line-range params to read_file_util."""
    mock_read_file_util.return_value = "5\u2192line five\n6\u2192line six\n"

    result = tools["read_file"](
        "some_file.py",
        start_line=5,
        end_line=10,
        with_line_numbers=True,
    )

    assert result == "5\u2192line five\n6\u2192line six\n"
    mock_read_file_util.assert_called_once_with(
        "some_file.py",
        project_dir=project_dir,
        start_line=5,
        end_line=10,
        with_line_numbers=True,
        max_lines=DEFAULT_READ_MAX_LINES,
    )


def test_read_file_truncates_full_read_at_configured_limit(
    project_dir: Path, make_tools: Callable[..., ToolMap]
) -> None:
    """A full read beyond the configured limit is cut with a paging note."""
    tools = make_tools(read_max_lines=3)
    (project_dir / "five.txt").write_text("a\nb\nc\nd\ne\n")

    content = tools["read_file"]("five.txt")

    assert content == (
        "a\nb\nc\n"
        "[truncated: showing lines 1–3 of 5; continue with start_line=4, end_line=5]"
    )


# --- Content type rejection tests ---


@pytest.mark.parametrize("name", ["save_file", "append_file"])
def test_rejects_non_string_content(
    name: str, project_dir: Path, tools: ToolMap
) -> None:
    """save_file and append_file reject non-string content with ValueError."""
    # Create a file for append_file to target
    target = project_dir / TEST_DIR / "type_test.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing")

    with pytest.raises(ValueError, match="Content must be a string"):
        tools[name](str(TEST_DIR / "type_test.txt"), {"key": "value"})


# --- Git read-only operation tool tests ---


class TestGitTool:
    """Tests for the unified git server wrapper."""

    @pytest.mark.asyncio
    @patch("mcp_workspace.git_operations.read_operations.git")
    async def test_delegates_to_impl(
        self, mock_impl: MagicMock, project_dir: Path, tools: ToolMap
    ) -> None:
        """Verify git() delegates all params to git_impl."""
        mock_impl.return_value = "output"
        result = await tools["git"](
            command="log",
            args=["--oneline"],
            pathspec=["src/"],
            search="fix",
            context=5,
            max_lines=25,
            compact=False,
        )
        assert result == "output"
        mock_impl.assert_called_once_with(
            command="log",
            project_dir=project_dir,
            args=["--oneline"],
            pathspec=["src/"],
            search="fix",
            context=5,
            max_lines=25,
            compact=False,
        )


# --- check_branch_status tool tests ---


class TestCheckBranchStatusTool:
    """Tests for the async check_branch_status MCP tool."""

    @pytest.mark.asyncio
    @patch(
        "mcp_workspace.checks.branch_status_polling.async_poll_branch_status",
        new_callable=AsyncMock,
    )
    async def test_check_branch_status_defaults(
        self, mock_poll: AsyncMock, project_dir: Path, tools: ToolMap
    ) -> None:
        """Default invocation forwards new defaults to async_poll_branch_status."""
        mock_poll.return_value = "report-text"

        result = await tools["check_branch_status"]()

        assert result == "report-text"
        mock_poll.assert_awaited_once_with(
            project_dir,
            max_log_lines=300,
            ci_timeout=300,
            pr_timeout=0,
            fail_on_reviews=False,
        )

    @pytest.mark.asyncio
    @patch(
        "mcp_workspace.checks.branch_status_polling.async_poll_branch_status",
        new_callable=AsyncMock,
    )
    async def test_check_branch_status_with_polling_params(
        self, mock_poll: AsyncMock, project_dir: Path, tools: ToolMap
    ) -> None:
        """Polling kwargs propagate to async_poll_branch_status."""
        mock_poll.return_value = "polled-report"

        result = await tools["check_branch_status"](
            max_log_lines=100,
            ci_timeout=180,
            pr_timeout=120,
        )

        assert result == "polled-report"
        mock_poll.assert_awaited_once_with(
            project_dir,
            max_log_lines=100,
            ci_timeout=180,
            pr_timeout=120,
            fail_on_reviews=False,
        )


# --- run_server tests ---


class TestRunServer:
    """Tests for run_server threading its settings into tool_specs."""

    def test_run_server_threads_reference_projects(self, project_dir: Path) -> None:
        """run_server passes reference_projects through to tool_specs and runs."""
        test_projects = {
            "proj1": ReferenceProject(
                name="proj1", path=Path("/path/to/proj1").resolve()
            ),
            "proj2": ReferenceProject(
                name="proj2", path=Path("/path/to/proj2").resolve()
            ),
        }

        with patch("mcp_workspace.server.FastMCP.run") as mock_run:
            with patch(
                "mcp_workspace.server.tool_specs", return_value=()
            ) as mock_specs:
                run_server(project_dir, reference_projects=test_projects)

        assert mock_specs.call_args.args == (project_dir,)
        assert mock_specs.call_args.kwargs["reference_projects"] == test_projects
        mock_run.assert_called_once()

    def test_run_server_default_reference_projects_is_none(
        self, project_dir: Path
    ) -> None:
        """run_server defaults reference_projects to None when omitted."""
        with patch("mcp_workspace.server.FastMCP.run"):
            with patch(
                "mcp_workspace.server.tool_specs", return_value=()
            ) as mock_specs:
                run_server(project_dir)

        assert mock_specs.call_args.kwargs["reference_projects"] is None

    def test_run_server_threads_read_max_lines(self, project_dir: Path) -> None:
        """run_server passes read_max_lines through to tool_specs."""
        with patch("mcp_workspace.server.FastMCP.run"):
            with patch(
                "mcp_workspace.server.tool_specs", return_value=()
            ) as mock_specs:
                run_server(project_dir, read_max_lines=7)

        assert mock_specs.call_args.args == (project_dir,)
        assert mock_specs.call_args.kwargs["read_max_lines"] == 7

    def test_run_server_defaults_read_max_lines(self, project_dir: Path) -> None:
        """Without read_max_lines, tool_specs gets DEFAULT_READ_MAX_LINES."""
        with patch("mcp_workspace.server.FastMCP.run"):
            with patch(
                "mcp_workspace.server.tool_specs", return_value=()
            ) as mock_specs:
                run_server(project_dir)

        assert mock_specs.call_args.kwargs["read_max_lines"] == DEFAULT_READ_MAX_LINES

    def test_run_server_logs_reference_projects(
        self, project_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """run_server logs its settings and each reference project at INFO."""
        proj_path = Path("/path/to/proj1").resolve()
        test_projects = {"proj1": ReferenceProject(name="proj1", path=proj_path)}

        with patch("mcp_workspace.server.FastMCP.run"):
            with patch("mcp_workspace.server.tool_specs", return_value=()):
                with caplog.at_level(logging.INFO, logger="mcp_workspace.server"):
                    run_server(project_dir, reference_projects=test_projects)

        assert any(
            m.startswith(f"Server settings: project_dir={project_dir},")
            for m in caplog.messages
        )
        assert f"Reference project 'proj1' set to: {proj_path}" in caplog.messages


# --- create_server / FastMCPSink tests ---

SNAPSHOT_TOOL_NAMES = sorted(
    path.stem
    for path in (Path(__file__).parent / "toolset" / "tool_schemas").glob("*.json")
)


class TestCreateServer:
    """Tests for create_server and FastMCPSink."""

    def test_returns_fresh_server_each_call(self, tmp_path: Path) -> None:
        """Two calls build two distinct FastMCP objects."""
        first = create_server(tmp_path)
        second = create_server(tmp_path)

        assert isinstance(first, FastMCP)
        assert isinstance(second, FastMCP)
        assert first is not second

    @pytest.mark.asyncio
    async def test_each_server_lists_all_tools(self, tmp_path: Path) -> None:
        """Every server built lists the full tool set."""
        for mcp in (create_server(tmp_path), create_server(tmp_path)):
            names = sorted(tool.name for tool in await mcp.list_tools())
            assert names == SNAPSHOT_TOOL_NAMES

    @pytest.mark.asyncio
    async def test_sink_registers_spec_name_and_description(self) -> None:
        """FastMCPSink.add registers under spec.name with spec.description."""

        def _probe(text: str) -> str:
            """Original docstring."""
            return text

        spec = tool_spec(
            _probe,
            group="test.probe",
            read_only=True,
            name="probe_tool",
            description="Probe description.",
        )
        mcp = FastMCP("probe")

        FastMCPSink(mcp).add(spec)

        tools = {tool.name: tool for tool in await mcp.list_tools()}
        assert list(tools) == ["probe_tool"]
        assert tools["probe_tool"].description == "Probe description."
