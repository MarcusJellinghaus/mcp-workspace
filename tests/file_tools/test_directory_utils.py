"""Tests for directory_utils functionality."""

from pathlib import Path
from unittest.mock import patch

import pytest

# Import functions directly from the module
from mcp_workspace.file_tools.directory_utils import (
    _discover_files,
    is_path_gitignored,
    list_files,
)
from mcp_workspace.utils.git_paths import is_path_in_git_dir
from tests.conftest import TEST_DIR


def test_discover_files(project_dir: Path) -> None:
    """Test discovering files in a directory recursively."""
    # Create test directory structure
    test_dir = project_dir / TEST_DIR

    # Create a subdirectory for testing recursion
    subdir = test_dir / "subdir"
    subdir.mkdir(exist_ok=True)

    # Create test files
    test_files = [test_dir / "test1.txt", test_dir / "test2.txt", subdir / "test3.txt"]

    for file_path in test_files:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"Content for {file_path.name}")

    # Test file discovery
    discovered_files = _discover_files(test_dir, project_dir)

    # Convert to a set for easy comparison
    rel_paths = {str(Path(f)) for f in discovered_files}
    expected_paths = {
        str(Path("testdata/test_file_tools/test1.txt")),
        str(Path("testdata/test_file_tools/test2.txt")),
        str(Path("testdata/test_file_tools/subdir/test3.txt")),
    }

    # Check if all expected files were discovered
    assert rel_paths.issuperset(expected_paths)

    # Discovered paths are forward-slash separated on every platform (issue #297)
    assert not any("\\" in f for f in discovered_files)


def test_git_directory_exclusion(project_dir: Path) -> None:
    """Test that .git directory is excluded from file discovery."""
    # Create test directory structure
    test_dir = project_dir / TEST_DIR

    # Create a .git directory with some files in it
    git_dir = test_dir / ".git"
    git_dir.mkdir(exist_ok=True)

    # Create some files in the test directory and in the .git directory
    regular_file = test_dir / "regular.txt"
    git_file = git_dir / "git_config.txt"

    regular_file.write_text("Regular file content")
    git_file.write_text("Git file content")

    # Discover files
    discovered_files = _discover_files(test_dir, project_dir)

    # Convert to a set of paths for easier assertion
    discovered_paths = set(discovered_files)

    # Discovered paths are forward-slash separated on every platform
    regular_path = "testdata/test_file_tools/regular.txt"
    git_path = "testdata/test_file_tools/.git/git_config.txt"

    # Assert that the regular file is included
    assert regular_path in discovered_paths

    # Assert that the git file is excluded
    assert git_path not in discovered_paths


@pytest.mark.parametrize(
    "path, expected",
    [
        (".git/config", True),
        (".git/hooks/pre-commit", True),
        ("src/main.py", False),
        (".gitignore", False),
        (".git", True),
    ],
)
def test_is_path_in_git_dir(path: str, expected: bool) -> None:
    """Check if path is correctly identified as inside .git directory."""
    assert is_path_in_git_dir(path) == expected


class TestIsPathGitignored:
    """Tests for is_path_gitignored()."""

    def test_git_dir_path_always_ignored(self, project_dir: Path) -> None:
        """Paths inside .git/ are always ignored, even without a .gitignore."""
        assert is_path_gitignored(".git/config", project_dir) is True
        assert is_path_gitignored(".git/hooks/pre-commit", project_dir) is True

    def test_no_gitignore_file(self, project_dir: Path) -> None:
        """Without a .gitignore, non-.git paths are not ignored."""
        # Ensure no .gitignore exists
        gitignore = project_dir / ".gitignore"
        if gitignore.exists():
            gitignore.unlink()
        assert is_path_gitignored("src/main.py", project_dir) is False

    def test_matched_pattern(self, project_dir: Path) -> None:
        """A path matching a .gitignore pattern is ignored."""
        (project_dir / ".gitignore").write_text("*.log\n")
        assert is_path_gitignored("debug.log", project_dir) is True
        assert is_path_gitignored("logs/error.log", project_dir) is True

    def test_unmatched_pattern(self, project_dir: Path) -> None:
        """A path not matching any .gitignore pattern is not ignored."""
        (project_dir / ".gitignore").write_text("*.log\n")
        assert is_path_gitignored("src/main.py", project_dir) is False

    def test_directory_pattern(self, project_dir: Path) -> None:
        """Directory patterns in .gitignore are respected."""
        (project_dir / ".gitignore").write_text("node_modules/\n")
        assert is_path_gitignored("node_modules/pkg/index.js", project_dir) is True

    def test_nonexistent_path(self, project_dir: Path) -> None:
        """Works on paths that don't exist on disk (e.g., pre-save check)."""
        (project_dir / ".gitignore").write_text("*.log\n")
        # File does not exist, but pattern still matches
        assert is_path_gitignored("future/new.log", project_dir) is True
        assert is_path_gitignored("future/new.txt", project_dir) is False

    def test_gitignore_itself_not_ignored(self, project_dir: Path) -> None:
        """.gitignore file itself is not ignored."""
        (project_dir / ".gitignore").write_text("*.log\n")
        assert is_path_gitignored(".gitignore", project_dir) is False


def test_list_files_basic(project_dir: Path) -> None:
    """Test listing files in a directory."""
    # Create test directory structure
    test_dir = project_dir / TEST_DIR

    # Create test files
    test_files = [test_dir / "test1.txt", test_dir / "test2.txt"]

    for file_path in test_files:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"Content for {file_path.name}")

    files = list_files(str(TEST_DIR), project_dir=project_dir)

    # The files should match exactly
    assert set(files) == {
        "testdata/test_file_tools/test1.txt",
        "testdata/test_file_tools/test2.txt",
    }


def test_list_files_with_gitignore(project_dir: Path) -> None:
    """Test listing files with gitignore filtering."""
    # Create test directory structure
    test_dir = project_dir / TEST_DIR

    # Create test files including ones to be ignored
    (test_dir / "keep.txt").write_text("keep this file")
    (test_dir / "ignore.log").write_text("ignore this file")

    # Create .gitignore file
    gitignore_path = test_dir / ".gitignore"
    gitignore_path.write_text("*.log")

    # Test listing files with gitignore filtering
    files = list_files(str(TEST_DIR), project_dir=project_dir, use_gitignore=True)

    # The .log file should be filtered out
    assert "testdata/test_file_tools/keep.txt" in files
    assert not any(f.endswith("ignore.log") for f in files)

    # A root .gitignore applies to the listing of a subdirectory (#392)
    (test_dir / "x.env").write_text("ignore this file")
    (project_dir / ".gitignore").write_text("*.env\n")

    files = list_files(str(TEST_DIR), project_dir=project_dir, use_gitignore=True)

    assert "testdata/test_file_tools/keep.txt" in files
    assert "testdata/test_file_tools/x.env" not in files


def test_list_files_without_gitignore(project_dir: Path) -> None:
    """Test listing files without gitignore filtering."""
    # Create test directory structure
    test_dir = project_dir / TEST_DIR

    # Create test files including ones normally ignored
    (test_dir / "keep.txt").write_text("keep this file")
    (test_dir / "dont_ignore.log").write_text("don't ignore this file")

    # Create .gitignore file
    gitignore_path = test_dir / ".gitignore"
    gitignore_path.write_text("*.log")

    # Mock the discovery
    with patch(
        "mcp_workspace.file_tools.directory_utils._discover_files"
    ) as mock_discover:
        # Configure the mock to return both files
        mock_discover.return_value = [
            "testdata/test_file_tools/keep.txt",
            "testdata/test_file_tools/dont_ignore.log",
        ]

        # Test listing files without gitignore filtering
        files = list_files(str(TEST_DIR), project_dir=project_dir, use_gitignore=False)

        # Both files should be included
        assert set(files) == {
            "testdata/test_file_tools/keep.txt",
            "testdata/test_file_tools/dont_ignore.log",
        }


def test_list_files_directory_not_found(project_dir: Path) -> None:
    """Test listing files in a non-existent directory."""
    non_existent_dir = "testdata/non_existent_dir"

    # Test with a non-existent directory
    with pytest.raises(FileNotFoundError) as excinfo:
        list_files(non_existent_dir, project_dir=project_dir)

    # Verify the error message
    assert f"Directory '{non_existent_dir}' does not exist" in str(excinfo.value)


def test_list_files_not_a_directory(project_dir: Path) -> None:
    """Test listing files on a path that is not a directory."""
    # Create a file
    test_file = project_dir / TEST_DIR / "not_a_dir.txt"
    test_file.write_text("This is not a directory")

    # Test with a file path instead of a directory
    with pytest.raises(NotADirectoryError) as excinfo:
        list_files(str(TEST_DIR / "not_a_dir.txt"), project_dir=project_dir)

    # Verify the error message
    assert "is not a directory" in str(excinfo.value)


def test_list_files_with_exception(project_dir: Path) -> None:
    """Test handling of unexpected exceptions in list_files."""
    # Mock _discover_files to raise an exception
    with patch(
        "mcp_workspace.file_tools.directory_utils._discover_files",
        side_effect=Exception("Test error"),
    ):
        # Test with a mocked exception
        with pytest.raises(Exception) as excinfo:
            list_files(str(TEST_DIR), project_dir=project_dir)

        # Verify that the exception is propagated
        assert "Test error" in str(excinfo.value)
