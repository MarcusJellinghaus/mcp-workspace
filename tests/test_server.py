"""Tests for the MCP server API endpoints."""

from pathlib import Path
from typing import Callable, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_workspace.server import (
    append_file,
    check_branch_status,
    delete_this_file,
    edit_file,
    git,
    list_directory,
    move_file,
    read_file,
    save_file,
    set_project_dir,
)

# Python path is now configured via pytest configuration in pyproject.toml

# Test constants
TEST_DIR = Path("testdata/test_file_tools")
TEST_FILE = TEST_DIR / "test_api_file.txt"
TEST_CONTENT = "This is API test content."


@pytest.fixture(autouse=True)
def setup_server(project_dir: Path) -> Generator[None, None, None]:
    """Setup the server with the project directory."""
    set_project_dir(project_dir)
    yield


def setup_function() -> None:
    """Setup for each test function."""
    # Ensure the test directory exists
    TEST_DIR.mkdir(parents=True, exist_ok=True)


def teardown_function() -> None:
    """Teardown for each test function."""
    # Clean up any test files
    if TEST_FILE.exists():
        TEST_FILE.unlink()


def test_save_file(project_dir: Path) -> None:
    """Test the save_file tool."""
    result = save_file(str(TEST_FILE), TEST_CONTENT)

    # Create absolute path for verification
    abs_file_path = project_dir / TEST_FILE

    assert result is True
    assert abs_file_path.exists()

    with open(abs_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == TEST_CONTENT


def test_read_file(project_dir: Path) -> None:
    """Test the read_file tool."""
    # Create absolute path for test file
    abs_file_path = project_dir / TEST_FILE

    # Create a test file
    with open(abs_file_path, "w", encoding="utf-8") as f:
        f.write(TEST_CONTENT)

    content = read_file(str(TEST_FILE))

    assert content == TEST_CONTENT


def test_read_file_not_found() -> None:
    """Test the read_file tool with a non-existent file."""
    non_existent_file = TEST_DIR / "non_existent.txt"

    # Ensure the file doesn't exist
    if Path(non_existent_file).exists():
        Path(non_existent_file).unlink()

    with pytest.raises(FileNotFoundError):
        read_file(str(non_existent_file))


def test_append_file(project_dir: Path) -> None:
    """Test the append_file tool."""
    # Create absolute path for test file
    abs_file_path = project_dir / TEST_FILE

    # Create initial content
    initial_content = "Initial content.\n"
    with open(abs_file_path, "w", encoding="utf-8") as f:
        f.write(initial_content)

    # Append content to the file
    append_content = "Appended content."
    result = append_file(str(TEST_FILE), append_content)

    # Verify the file was updated
    assert result is True
    assert abs_file_path.exists()

    # Verify the combined content
    expected_content = initial_content + append_content
    with open(abs_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == expected_content


def test_append_file_empty(project_dir: Path) -> None:
    """Test appending to an empty file."""
    # Create the empty file
    empty_file = TEST_DIR / "empty_file.txt"
    abs_file_path = project_dir / empty_file
    with open(abs_file_path, "w", encoding="utf-8") as f:
        pass  # Create an empty file

    # Append content to the empty file
    append_content = "Content added to empty file."
    result = append_file(str(empty_file), append_content)

    # Verify the file was updated
    assert result is True
    assert abs_file_path.exists()

    # Verify the content
    with open(abs_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == append_content


def test_append_file_not_found() -> None:
    """Test appending to a file that doesn't exist."""
    non_existent_file = TEST_DIR / "non_existent_append.txt"

    # Ensure the file doesn't exist
    if Path(non_existent_file).exists():
        Path(non_existent_file).unlink()

    # Test appending to a non-existent file
    with pytest.raises(FileNotFoundError):
        append_file(str(non_existent_file), "This should fail")


@patch("mcp_workspace.server.list_directory_tree")
@patch("mcp_workspace.server.list_files_util")
def test_list_directory(
    mock_list_files: MagicMock, mock_tree: MagicMock, project_dir: Path
) -> None:
    """Test the list_directory tool with default args (backward compatible)."""
    # Create absolute path for test file
    abs_file_path = project_dir / TEST_FILE

    # Create a test file
    with open(abs_file_path, "w", encoding="utf-8") as f:
        f.write(TEST_CONTENT)

    # Mock the list_files function to return our test file
    mock_list_files.return_value = [str(TEST_FILE)]
    mock_tree.return_value = [str(TEST_FILE)]

    files = list_directory()

    # Verify the function was called with correct parameters
    mock_list_files.assert_called_once_with(
        ".", project_dir=project_dir, use_gitignore=True
    )
    mock_tree.assert_called_once_with([str(TEST_FILE)], base_path=".", dirs_only=False)

    assert str(TEST_FILE) in files


@patch("mcp_workspace.server.list_files_util")
def test_list_directory_directory_not_found(
    mock_list_files: MagicMock, project_dir: Path  # pylint: disable=unused-argument
) -> None:
    """Test the list_directory tool with a non-existent directory."""
    # Mock list_files to raise FileNotFoundError
    mock_list_files.side_effect = FileNotFoundError("Directory not found")

    with pytest.raises(FileNotFoundError):
        list_directory()


@patch("mcp_workspace.server.list_directory_tree")
@patch("mcp_workspace.server.list_files_util")
def test_list_directory_with_gitignore(
    mock_list_files: MagicMock, mock_tree: MagicMock, project_dir: Path
) -> None:
    """Test the list_directory tool with gitignore filtering."""
    # Mock list_files to return filtered files
    mock_list_files.return_value = [
        str(TEST_DIR / "test_normal.txt"),
        str(TEST_DIR / ".gitignore"),
    ]
    mock_tree.return_value = [
        str(TEST_DIR / "test_normal.txt"),
        str(TEST_DIR / ".gitignore"),
    ]

    files = list_directory()

    # Verify the function was called with gitignore=True
    mock_list_files.assert_called_once_with(
        ".", project_dir=project_dir, use_gitignore=True
    )

    assert str(TEST_DIR / "test_normal.txt") in files
    assert str(TEST_DIR / ".gitignore") in files


@patch("mcp_workspace.server.list_files_util")
def test_list_directory_error_handling(
    mock_list_files: MagicMock, project_dir: Path
) -> None:
    """Test error handling in the list_directory tool."""
    # Mock list_files to raise an exception
    mock_list_files.side_effect = Exception("Test error")

    with pytest.raises(Exception):
        list_directory()


@patch("mcp_workspace.server.list_directory_tree")
@patch("mcp_workspace.server.list_files_util")
def test_list_directory_path_parameter(
    mock_list_files: MagicMock, mock_tree: MagicMock, project_dir: Path
) -> None:
    """Test list_directory with path parameter scopes to subtree."""
    # Create src directory
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "app.py").write_text("# app")

    mock_list_files.return_value = ["src/app.py"]
    mock_tree.return_value = ["src/app.py"]

    files = list_directory(path="src")

    mock_list_files.assert_called_once_with(
        "src", project_dir=project_dir, use_gitignore=True
    )
    mock_tree.assert_called_once_with(["src/app.py"], base_path="src", dirs_only=False)
    assert "src/app.py" in files


@patch("mcp_workspace.server.list_directory_tree")
@patch("mcp_workspace.server.list_files_util")
def test_list_directory_dirs_only(
    mock_list_files: MagicMock, mock_tree: MagicMock, project_dir: Path
) -> None:
    """Test list_directory with dirs_only=True returns only directory paths."""
    mock_list_files.return_value = ["src/app.py", "tests/test_app.py"]
    mock_tree.return_value = ["src/", "tests/"]

    files = list_directory(dirs_only=True)

    mock_list_files.assert_called_once_with(
        ".", project_dir=project_dir, use_gitignore=True
    )
    mock_tree.assert_called_once_with(
        ["src/app.py", "tests/test_app.py"], base_path=".", dirs_only=True
    )
    assert files == ["src/", "tests/"]


def test_list_directory_path_is_file(project_dir: Path) -> None:
    """Test list_directory raises ValueError when path points to a file."""
    # Create a file to point at
    test_file = project_dir / "README.md"
    test_file.write_text("# readme")

    with pytest.raises(ValueError, match="is a file"):
        list_directory(path="README.md")


def test_list_directory_path_not_found(project_dir: Path) -> None:
    """Test list_directory raises FileNotFoundError for non-existent path."""
    with pytest.raises(FileNotFoundError):
        list_directory(path="nonexistent_dir")


def test_list_directory_path_traversal(project_dir: Path) -> None:
    """Test list_directory blocks path traversal attacks."""
    with pytest.raises(ValueError):
        list_directory(path="../../etc")


@patch("mcp_workspace.server.list_directory_tree")
@patch("mcp_workspace.server.list_files_util")
def test_list_directory_path_trailing_slash(
    mock_list_files: MagicMock, mock_tree: MagicMock, project_dir: Path
) -> None:
    """Test list_directory with trailing slash behaves identically to without."""
    # Create src directory
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "app.py").write_text("# app")

    mock_list_files.return_value = ["src/app.py"]
    mock_tree.return_value = ["src/app.py"]

    files = list_directory(path="src/")

    mock_list_files.assert_called_once_with(
        "src/", project_dir=project_dir, use_gitignore=True
    )
    assert "src/app.py" in files


# --- Integration tests for list_directory path / dirs_only ---


def test_list_directory_path_is_file_integration(project_dir: Path) -> None:
    """Integration: list_directory(path=<file>) returns a clear error."""
    f = project_dir / "some_file.py"
    f.write_text("x = 1")
    with pytest.raises(ValueError, match="is a file"):
        list_directory(path="some_file.py")


def test_list_directory_path_nonexistent_integration(project_dir: Path) -> None:
    """Integration: list_directory(path=<missing>) returns file-not-found."""
    with pytest.raises(FileNotFoundError):
        list_directory(path="nonexistent")


def test_list_directory_dirs_only_integration(project_dir: Path) -> None:
    """Integration: list_directory(dirs_only=True) returns only directories."""
    sub = project_dir / "mydir"
    sub.mkdir()
    (sub / "child.txt").write_text("hi")
    (project_dir / "root.txt").write_text("root")

    result = list_directory(dirs_only=True)

    # Should contain directory entries but no plain file entries
    assert any("mydir" in entry for entry in result)
    assert not any(entry.endswith(".txt") for entry in result)


def test_list_directory_path_subtree_integration(project_dir: Path) -> None:
    """Integration: list_directory(path=<subdir>) scopes to that subtree."""
    sub = project_dir / "sub"
    sub.mkdir()
    (sub / "a.py").write_text("a")
    (project_dir / "root.py").write_text("root")

    result = list_directory(path="sub")

    # Subtree listing should contain the file inside sub
    assert any("a.py" in entry for entry in result)
    # Should NOT contain root.py
    assert not any("root.py" in entry for entry in result)


def test_move_file(project_dir: Path) -> None:
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
    result = move_file(str(source_file), str(dest_file))

    assert result is True
    assert not abs_source.exists()
    assert abs_dest.exists()
    with open(abs_dest, "r", encoding="utf-8") as f:
        assert f.read() == "Test content"

    # Clean up
    if abs_dest.exists():
        abs_dest.unlink()


def test_move_file_simplified_errors(project_dir: Path) -> None:
    """Test that server endpoint returns simplified error messages."""
    # Test file not found
    with pytest.raises(FileNotFoundError) as exc_info:
        move_file("nonexistent.txt", "dest.txt")
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
        move_file(str(source_file), str(dest_file))
    assert str(exc_info2.value) == "Destination already exists"  # Simple message

    # Clean up
    if abs_source.exists():
        abs_source.unlink()
    if abs_dest.exists():
        abs_dest.unlink()


@patch("mcp_workspace.server.move_file_util")
def test_move_file_permission_error(mock_move: MagicMock, project_dir: Path) -> None:
    """Test permission error handling in move_file."""
    # Mock move_file_util to raise PermissionError
    mock_move.side_effect = PermissionError("Access denied to file: /some/path")

    with pytest.raises(PermissionError) as exc:
        move_file("readonly.txt", "dest.txt")
    assert str(exc.value) == "Permission denied"  # Simple message


@patch("mcp_workspace.server.move_file_util")
def test_move_file_security_error(mock_move: MagicMock, project_dir: Path) -> None:
    """Test security error handling in move_file."""
    # Mock move_file_util to raise ValueError with security message
    mock_move.side_effect = ValueError("Security: Path outside project directory")

    with pytest.raises(ValueError) as exc:
        move_file("../outside.txt", "dest.txt")
    assert str(exc.value) == "Invalid path"  # Simple message


@patch("mcp_workspace.server.move_file_util")
def test_move_file_generic_error(mock_move: MagicMock, project_dir: Path) -> None:
    """Test generic error handling in move_file."""
    # Import move_file here to avoid issues if not yet implemented
    from mcp_workspace.server import move_file as move_file_fn

    # Mock move_file_util to raise a generic exception
    mock_move.side_effect = RuntimeError("Some complex internal error")

    with pytest.raises(RuntimeError) as exc:
        move_file_fn("source.txt", "dest.txt")
    assert str(exc.value) == "Move operation failed"  # Simple message


# --- Gitignore enforcement tests ---


@pytest.fixture
def gitignore_project(project_dir: Path) -> Path:
    """Project dir with a .gitignore that blocks *.log and __pycache__/."""
    (project_dir / ".gitignore").write_text("*.log\n__pycache__/\n")
    return project_dir


def test_read_file_gitignored(gitignore_project: Path) -> None:
    """read_file on gitignored file raises ValueError."""
    (gitignore_project / "debug.log").write_text("log content")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        read_file("debug.log")


def test_save_file_gitignored(gitignore_project: Path) -> None:
    """save_file to gitignored path raises ValueError."""
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        save_file("output.log", "content")


@pytest.mark.asyncio
async def test_edit_file_gitignored(gitignore_project: Path) -> None:
    """edit_file on gitignored file raises ValueError."""
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        await edit_file("debug.log", old_string="a", new_string="b")


def test_append_file_gitignored(gitignore_project: Path) -> None:
    """append_file to gitignored file raises ValueError."""
    (gitignore_project / "debug.log").write_text("existing")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        append_file("debug.log", "more")


def test_delete_file_gitignored(gitignore_project: Path) -> None:
    """delete_this_file on gitignored file raises ValueError."""
    (gitignore_project / "debug.log").write_text("to delete")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        delete_this_file("debug.log")


def test_move_file_gitignored_source(gitignore_project: Path) -> None:
    """move_file with gitignored source raises ValueError."""
    (gitignore_project / "debug.log").write_text("content")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        move_file("debug.log", "renamed.txt")


def test_move_file_gitignored_destination(gitignore_project: Path) -> None:
    """move_file with gitignored destination raises ValueError."""
    (gitignore_project / "safe.txt").write_text("content")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        move_file("safe.txt", "output.log")


def test_read_file_in_gitignored_directory(gitignore_project: Path) -> None:
    """File inside gitignored directory (__pycache__/) is blocked."""
    cache_dir = gitignore_project / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "module.pyc").write_text("bytecode")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        read_file("__pycache__/module.pyc")


def test_read_file_git_config(gitignore_project: Path) -> None:
    """read_file on .git/config is blocked."""
    git_dir = gitignore_project / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        read_file(".git/config")


def test_save_file_git_hooks(gitignore_project: Path) -> None:
    """save_file to .git/hooks/ is blocked."""
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        save_file(".git/hooks/pre-commit", "#!/bin/sh")


def test_read_file_not_gitignored(gitignore_project: Path) -> None:
    """Non-gitignored file works normally."""
    (gitignore_project / "readme.txt").write_text("hello")
    content = read_file("readme.txt")
    assert content == "hello"


def test_save_file_not_gitignored(gitignore_project: Path) -> None:
    """Non-gitignored save works normally."""
    result = save_file("readme.txt", "hello")
    assert result is True


def test_read_file_no_gitignore(project_dir: Path) -> None:
    """Without .gitignore, all files are accessible."""
    (project_dir / "debug.log").write_text("log content")
    content = read_file("debug.log")
    assert content == "log content"


@patch("mcp_workspace.server.read_file_util")
def test_read_file_forwards_line_range_params(
    mock_read_file_util: MagicMock, project_dir: Path
) -> None:
    """Test that read_file forwards line-range params to read_file_util."""
    mock_read_file_util.return_value = "5\u2192line five\n6\u2192line six\n"

    result = read_file(
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
    )


# --- Content type rejection tests ---


@pytest.mark.parametrize("func", [save_file, append_file])
def test_rejects_non_string_content(
    func: Callable[..., bool], project_dir: Path
) -> None:
    """save_file and append_file reject non-string content with ValueError."""
    # Create a file for append_file to target
    target = project_dir / TEST_DIR / "type_test.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing")

    with pytest.raises(ValueError, match="Content must be a string"):
        func(str(TEST_DIR / "type_test.txt"), {"key": "value"})


# --- Git read-only operation tool tests ---


class TestGitTool:
    """Tests for the unified git server wrapper."""

    @pytest.mark.asyncio
    @patch("mcp_workspace.server.git_impl")
    async def test_delegates_to_impl(
        self, mock_impl: MagicMock, project_dir: Path
    ) -> None:
        """Verify git() delegates all params to git_impl."""
        mock_impl.return_value = "output"
        result = await git(
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

    @pytest.mark.asyncio
    async def test_raises_without_project_dir(self) -> None:
        """git() raises ValueError when _project_dir is None."""
        import mcp_workspace.server as srv

        original = srv._project_dir
        try:
            srv._project_dir = None
            with pytest.raises(ValueError, match="Project directory has not been set"):
                await git(command="log")
        finally:
            srv._project_dir = original


# --- check_branch_status tool tests ---


class TestCheckBranchStatusTool:
    """Tests for the async check_branch_status MCP tool."""

    @pytest.mark.asyncio
    @patch("mcp_workspace.server.async_poll_branch_status", new_callable=AsyncMock)
    async def test_check_branch_status_defaults(
        self, mock_poll: AsyncMock, project_dir: Path
    ) -> None:
        """Default invocation forwards new defaults to async_poll_branch_status."""
        mock_poll.return_value = "report-text"

        result = await check_branch_status()

        assert result == "report-text"
        mock_poll.assert_awaited_once_with(
            project_dir,
            max_log_lines=300,
            ci_timeout=300,
            pr_timeout=0,
        )

    @pytest.mark.asyncio
    @patch("mcp_workspace.server.async_poll_branch_status", new_callable=AsyncMock)
    async def test_check_branch_status_with_polling_params(
        self, mock_poll: AsyncMock, project_dir: Path
    ) -> None:
        """Polling kwargs propagate to async_poll_branch_status."""
        mock_poll.return_value = "polled-report"

        result = await check_branch_status(
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
        )

    @pytest.mark.asyncio
    async def test_check_branch_status_no_project_dir(self) -> None:
        """check_branch_status raises ValueError when _project_dir is None."""
        import mcp_workspace.server as srv

        original = srv._project_dir
        try:
            srv._project_dir = None
            with pytest.raises(ValueError, match="Project directory has not been set"):
                await check_branch_status()
        finally:
            srv._project_dir = original
