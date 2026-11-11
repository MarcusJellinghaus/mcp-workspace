"""Tests for the list_directory MCP server tool."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import ToolMap

TEST_DIR = Path("testdata/test_file_tools")
TEST_FILE = TEST_DIR / "test_api_file.txt"
TEST_CONTENT = "This is API test content."


@patch("mcp_workspace.toolset.read.list_directory_tree")
@patch("mcp_workspace.toolset.read.list_files_util")
def test_list_directory(
    mock_list_files: MagicMock,
    mock_tree: MagicMock,
    project_dir: Path,
    tools: ToolMap,
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

    files = tools["list_directory"]()

    # Verify the function was called with correct parameters
    mock_list_files.assert_called_once_with(
        ".", project_dir=project_dir, use_gitignore=True
    )
    mock_tree.assert_called_once_with([str(TEST_FILE)], base_path=".", dirs_only=False)

    assert str(TEST_FILE) in files


@patch("mcp_workspace.toolset.read.list_files_util")
def test_list_directory_directory_not_found(
    mock_list_files: MagicMock,
    tools: ToolMap,
) -> None:
    """Test the list_directory tool with a non-existent directory."""
    # Mock list_files to raise FileNotFoundError
    mock_list_files.side_effect = FileNotFoundError("Directory not found")

    with pytest.raises(FileNotFoundError):
        tools["list_directory"]()


@patch("mcp_workspace.toolset.read.list_directory_tree")
@patch("mcp_workspace.toolset.read.list_files_util")
def test_list_directory_with_gitignore(
    mock_list_files: MagicMock,
    mock_tree: MagicMock,
    project_dir: Path,
    tools: ToolMap,
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

    files = tools["list_directory"]()

    # Verify the function was called with gitignore=True
    mock_list_files.assert_called_once_with(
        ".", project_dir=project_dir, use_gitignore=True
    )

    assert str(TEST_DIR / "test_normal.txt") in files
    assert str(TEST_DIR / ".gitignore") in files


@patch("mcp_workspace.toolset.read.list_files_util")
def test_list_directory_error_handling(
    mock_list_files: MagicMock, tools: ToolMap
) -> None:
    """Test error handling in the list_directory tool."""
    # Mock list_files to raise an exception it documents
    mock_list_files.side_effect = NotADirectoryError("Test error")

    with pytest.raises(NotADirectoryError, match="Test error"):
        tools["list_directory"]()


@patch("mcp_workspace.toolset.read.list_directory_tree")
@patch("mcp_workspace.toolset.read.list_files_util")
def test_list_directory_path_parameter(
    mock_list_files: MagicMock,
    mock_tree: MagicMock,
    project_dir: Path,
    tools: ToolMap,
) -> None:
    """Test list_directory with path parameter scopes to subtree."""
    # Create src directory
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "app.py").write_text("# app")

    mock_list_files.return_value = ["src/app.py"]
    mock_tree.return_value = ["src/app.py"]

    files = tools["list_directory"](path="src")

    mock_list_files.assert_called_once_with(
        "src", project_dir=project_dir, use_gitignore=True
    )
    mock_tree.assert_called_once_with(["src/app.py"], base_path="src", dirs_only=False)
    assert "src/app.py" in files


@patch("mcp_workspace.toolset.read.list_directory_tree")
@patch("mcp_workspace.toolset.read.list_files_util")
def test_list_directory_dirs_only(
    mock_list_files: MagicMock,
    mock_tree: MagicMock,
    project_dir: Path,
    tools: ToolMap,
) -> None:
    """Test list_directory with dirs_only=True returns only directory paths."""
    mock_list_files.return_value = ["src/app.py", "tests/test_app.py"]
    mock_tree.return_value = ["src/", "tests/"]

    files = tools["list_directory"](dirs_only=True)

    mock_list_files.assert_called_once_with(
        ".", project_dir=project_dir, use_gitignore=True
    )
    mock_tree.assert_called_once_with(
        ["src/app.py", "tests/test_app.py"], base_path=".", dirs_only=True
    )
    assert files == ["src/", "tests/"]


def test_list_directory_path_is_file(project_dir: Path, tools: ToolMap) -> None:
    """Test list_directory raises ValueError when path points to a file."""
    # Create a file to point at
    test_file = project_dir / "README.md"
    test_file.write_text("# readme")

    with pytest.raises(ValueError, match="is a file"):
        tools["list_directory"](path="README.md")


def test_list_directory_path_not_found(tools: ToolMap) -> None:
    """Test list_directory raises FileNotFoundError for non-existent path."""
    with pytest.raises(FileNotFoundError):
        tools["list_directory"](path="nonexistent_dir")


def test_list_directory_path_traversal(tools: ToolMap) -> None:
    """Test list_directory blocks path traversal attacks."""
    with pytest.raises(ValueError):
        tools["list_directory"](path="../../etc")


@patch("mcp_workspace.toolset.read.list_directory_tree")
@patch("mcp_workspace.toolset.read.list_files_util")
def test_list_directory_path_trailing_slash(
    mock_list_files: MagicMock,
    mock_tree: MagicMock,
    project_dir: Path,
    tools: ToolMap,
) -> None:
    """Test list_directory with trailing slash behaves identically to without."""
    # Create src directory
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "app.py").write_text("# app")

    mock_list_files.return_value = ["src/app.py"]
    mock_tree.return_value = ["src/app.py"]

    files = tools["list_directory"](path="src/")

    mock_list_files.assert_called_once_with(
        "src/", project_dir=project_dir, use_gitignore=True
    )
    assert "src/app.py" in files


# --- Integration tests for list_directory path / dirs_only ---


def test_list_directory_path_is_file_integration(
    project_dir: Path, tools: ToolMap
) -> None:
    """Integration: list_directory(path=<file>) returns a clear error."""
    f = project_dir / "some_file.py"
    f.write_text("x = 1")
    with pytest.raises(ValueError, match="is a file"):
        tools["list_directory"](path="some_file.py")


def test_list_directory_path_nonexistent_integration(tools: ToolMap) -> None:
    """Integration: list_directory(path=<missing>) returns file-not-found."""
    with pytest.raises(FileNotFoundError):
        tools["list_directory"](path="nonexistent")


def test_list_directory_dirs_only_integration(
    project_dir: Path, tools: ToolMap
) -> None:
    """Integration: list_directory(dirs_only=True) returns only directories."""
    sub = project_dir / "mydir"
    sub.mkdir()
    (sub / "child.txt").write_text("hi")
    (project_dir / "root.txt").write_text("root")

    result = tools["list_directory"](dirs_only=True)

    # Should contain directory entries but no plain file entries
    assert any("mydir" in entry for entry in result)
    assert not any(entry.endswith(".txt") for entry in result)


def test_list_directory_path_subtree_integration(
    project_dir: Path, tools: ToolMap
) -> None:
    """Integration: list_directory(path=<subdir>) scopes to that subtree."""
    sub = project_dir / "sub"
    sub.mkdir()
    (sub / "a.py").write_text("a")
    (project_dir / "root.py").write_text("root")

    result = tools["list_directory"](path="sub")

    # Subtree listing should contain the file inside sub, prefix present exactly once
    assert result == ["sub/a.py"]


_TREE_FILES = [
    "root.py",
    "sub/a.py",
    "sub/deep/b.py",
    "pkg/mod.py",
    "pkg/inner/other.py",
]


def _make_tree(project_dir: Path) -> None:
    """Create a small file tree whose content is each file's own relative path."""
    for rel in _TREE_FILES:
        path = project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel)


@pytest.mark.parametrize(
    "scope, expected",
    [
        (".", _TREE_FILES),
        ("sub", ["sub/deep/b.py", "sub/a.py"]),
        ("sub/deep", ["sub/deep/b.py"]),
        ("pkg", ["pkg/inner/other.py", "pkg/mod.py"]),
    ],
)
def test_list_directory_entries_are_valid_paths_integration(
    project_dir: Path, tools: ToolMap, scope: str, expected: list[str]
) -> None:
    """Integration: every returned entry is a path read_file accepts unmodified."""
    _make_tree(project_dir)

    result = tools["list_directory"](path=scope)

    # No entry is duplicated
    assert len(result) == len(set(result))
    assert set(expected) <= set(result)
    # Each file wrote its own relative path as content, so a correct entry round-trips
    for entry in expected:
        assert tools["read_file"](entry) == entry


def test_list_directory_dirs_only_subtree_integration(
    project_dir: Path, tools: ToolMap
) -> None:
    """Integration: dirs_only entries under a scope carry the prefix exactly once."""
    _make_tree(project_dir)

    assert tools["list_directory"](path="pkg", dirs_only=True) == ["pkg/inner/"]


# --- Integration tests for gitignored list_directory paths ---


def test_list_directory_refuses_ignored_directory(
    project_dir: Path, tools: ToolMap
) -> None:
    """Integration: listing an ignored directory is refused without leaking names."""
    (project_dir / ".gitignore").write_text("secret/\n")
    (project_dir / "secret").mkdir()
    (project_dir / "secret" / "key.txt").write_text("k")

    with pytest.raises(ValueError, match="excluded by .gitignore rules") as exc_info:
        tools["list_directory"]("secret")

    assert "key.txt" not in str(exc_info.value)


def test_list_directory_all_files_ignored_returns_empty(
    project_dir: Path, tools: ToolMap
) -> None:
    """Integration: a non-ignored directory whose files are all ignored lists empty."""
    (project_dir / ".gitignore").write_text("*.log\n")
    (project_dir / "logs").mkdir()
    (project_dir / "logs" / "a.log").write_text("log")

    assert tools["list_directory"]("logs") == []


def test_list_directory_root_not_refused_by_star_pattern(
    project_dir: Path, tools: ToolMap
) -> None:
    """Integration: the project root is never refused, even under a '*' rule."""
    (project_dir / ".gitignore").write_text("*\n!*/\n!*.py\n")
    (project_dir / "a.py").write_text("a")

    assert "a.py" in tools["list_directory"](".")
