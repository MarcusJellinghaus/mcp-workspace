"""Tests for git integration in move operations."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from git import Repo
from git.exc import GitCommandError

from mcp_workspace.file_tools.file_operations import move_file


class TestGitMoveIntegration:
    """Test git integration in move operations."""

    def test_move_tracked_file_uses_git(self, tmp_path: Path) -> None:
        """Test that tracked files are moved using git mv."""
        # Create a git repository
        repo = Repo.init(tmp_path)

        # Create and commit a file
        tracked_file = tmp_path / "tracked.txt"
        tracked_file.write_text("tracked content")
        repo.index.add([str(tracked_file)])
        repo.index.commit("Initial commit")

        # Move the tracked file
        result = move_file("tracked.txt", "moved_tracked.txt", project_dir=tmp_path)

        # Verify git was used
        assert result["success"] is True
        assert result["method"] == "git"
        assert "git mv" in result["message"].lower()

        # Verify file was moved
        assert not tracked_file.exists()
        moved_file = tmp_path / "moved_tracked.txt"
        assert moved_file.exists()
        assert moved_file.read_text() == "tracked content"

        # Verify git status shows the rename
        status = repo.git.status("--short")
        assert "R" in status  # R indicates renamed

    def test_move_untracked_file_uses_filesystem(self, tmp_path: Path) -> None:
        """Test that untracked files use filesystem operations even in git repo."""
        # Create a git repository
        Repo.init(tmp_path)

        # Create untracked file
        untracked_file = tmp_path / "untracked.txt"
        untracked_file.write_text("untracked content")

        # Move the untracked file
        result = move_file("untracked.txt", "moved_untracked.txt", project_dir=tmp_path)

        # Verify filesystem was used
        assert result["success"] is True
        assert result["method"] == "filesystem"

        # Verify file was moved
        assert not untracked_file.exists()
        moved_file = tmp_path / "moved_untracked.txt"
        assert moved_file.exists()

    def test_git_move_fallback_on_error(self, tmp_path: Path) -> None:
        """Test fallback to filesystem when git mv fails."""
        # Create a git repository
        repo = Repo.init(tmp_path)

        # Create and commit a file
        tracked_file = tmp_path / "tracked.txt"
        tracked_file.write_text("content")
        repo.index.add([str(tracked_file)])
        repo.index.commit("Initial commit")

        # Mock git_move to simulate a git mv failure. The move helper imports
        # git_move lazily from mcp_workspace.git_operations, so patch it there.
        with patch(
            "mcp_workspace.git_operations.git_move",
            side_effect=GitCommandError("git mv", 128),
        ):
            result = move_file("tracked.txt", "moved.txt", project_dir=tmp_path)

            # Should fall back to filesystem
            assert result["success"] is True
            assert result["method"] == "filesystem"
            assert "fallback" in result["message"].lower()

    def test_move_tracked_file_to_new_directory(self, tmp_path: Path) -> None:
        """Test moving a tracked file to a new directory with git."""
        # Create a git repository
        repo = Repo.init(tmp_path)

        # Create and commit a file
        tracked_file = tmp_path / "original.txt"
        tracked_file.write_text("content")
        repo.index.add([str(tracked_file)])
        repo.index.commit("Initial commit")

        # Move to new directory (parent dirs created automatically)
        result = move_file("original.txt", "newdir/moved.txt", project_dir=tmp_path)

        assert result["success"] is True
        assert result["method"] == "git"

        # Verify file was moved
        assert not tracked_file.exists()
        moved_file = tmp_path / "newdir" / "moved.txt"
        assert moved_file.exists()
        assert moved_file.read_text() == "content"

    def test_move_directory_with_tracked_files(self, tmp_path: Path) -> None:
        """Test moving a directory containing tracked files."""
        # Create a git repository
        repo = Repo.init(tmp_path)

        # Create directory with tracked files
        src_dir = tmp_path / "src_dir"
        src_dir.mkdir()
        file1 = src_dir / "tracked1.txt"
        file2 = src_dir / "tracked2.txt"
        file1.write_text("content 1")
        file2.write_text("content 2")

        repo.index.add([str(file1), str(file2)])
        repo.index.commit("Initial commit")

        # Move the directory
        result = move_file("src_dir", "dest_dir", project_dir=tmp_path)

        assert result["success"] is True
        assert result["method"] == "git"

        # Verify directory was moved
        assert not src_dir.exists()
        dest_dir = tmp_path / "dest_dir"
        assert dest_dir.exists()
        assert (dest_dir / "tracked1.txt").read_text() == "content 1"
        assert (dest_dir / "tracked2.txt").read_text() == "content 2"

    def test_move_non_git_repository(self, tmp_path: Path) -> None:
        """Test that move operations work in non-git directories."""
        # No git repository initialization
        # Create a file
        source_file = tmp_path / "normal.txt"
        source_file.write_text("normal content")

        # Move the file
        result = move_file("normal.txt", "moved_normal.txt", project_dir=tmp_path)

        # Verify filesystem was used
        assert result["success"] is True
        assert result["method"] == "filesystem"

        # Verify file was moved
        assert not source_file.exists()
        moved_file = tmp_path / "moved_normal.txt"
        assert moved_file.exists()
        assert moved_file.read_text() == "normal content"

    def test_move_file_with_staged_changes(self, tmp_path: Path) -> None:
        """Test moving a file that has staged changes."""
        # Create a git repository
        repo = Repo.init(tmp_path)

        # Create and commit a file
        tracked_file = tmp_path / "staged.txt"
        tracked_file.write_text("original content")
        repo.index.add([str(tracked_file)])
        repo.index.commit("Initial commit")

        # Modify the file and stage changes
        tracked_file.write_text("modified content")
        repo.index.add([str(tracked_file)])

        # Move the file
        result = move_file("staged.txt", "moved_staged.txt", project_dir=tmp_path)

        assert result["success"] is True
        assert result["method"] == "git"

        # Verify file was moved with changes preserved
        assert not tracked_file.exists()
        moved_file = tmp_path / "moved_staged.txt"
        assert moved_file.exists()
        assert moved_file.read_text() == "modified content"

        # Check that the changes are still staged
        diff_staged = repo.index.diff("HEAD", staged=True)
        # The file should appear as renamed in the staged changes
        assert any("moved_staged.txt" in str(diff) for diff in diff_staged)
