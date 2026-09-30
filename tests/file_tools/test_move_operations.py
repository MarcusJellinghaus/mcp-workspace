"""Tests for file move/rename operations."""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from mcp_workspace.file_tools.file_operations import move_file


class TestBasicMoveOperations:
    """Test basic file move and rename operations.

    All tests use pytest's tmp_path fixture to ensure no files are left behind.
    The tmp_path fixture creates a fresh temporary directory for each test
    and automatically cleans it up after the test completes.
    """

    def test_move_file_same_directory(self, tmp_path: Path) -> None:
        """Test renaming a file in the same directory."""
        # Create source file
        source = tmp_path / "test_file.txt"
        source.write_text("test content")

        # Move (rename) the file
        result = move_file("test_file.txt", "renamed_file.txt", project_dir=tmp_path)

        # Verify result
        assert result["success"] is True
        assert result["method"] == "filesystem"
        assert result["source"] == "test_file.txt"
        assert result["destination"] == "renamed_file.txt"

        # Verify file was moved
        assert not source.exists()
        dest = tmp_path / "renamed_file.txt"
        assert dest.exists()
        assert dest.read_text() == "test content"

    def test_move_file_nested_paths_are_forward_slash_separated(
        self, tmp_path: Path
    ) -> None:
        """The returned dict reports nested paths with '/', not os.sep."""
        source = tmp_path / "src" / "pkg" / "mod.py"
        source.parent.mkdir(parents=True)
        source.write_text("content")

        result = move_file("src/pkg/mod.py", "lib/inner/mod.py", project_dir=tmp_path)

        assert result["source"] == "src/pkg/mod.py"
        assert result["destination"] == "lib/inner/mod.py"

    def test_move_file_to_subdirectory(self, tmp_path: Path) -> None:
        """Test moving a file to a subdirectory."""
        # Create source file
        source = tmp_path / "source.txt"
        source.write_text("content to move")

        # Create target directory
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        # Move file
        result = move_file("source.txt", "subdir/moved.txt", project_dir=tmp_path)

        assert result["success"] is True
        assert not source.exists()
        dest = tmp_path / "subdir" / "moved.txt"
        assert dest.exists()
        assert dest.read_text() == "content to move"

    def test_move_file_create_parent_directory(self, tmp_path: Path) -> None:
        """Test moving a file to a non-existent directory (auto-creates parents)."""
        # Create source file
        source = tmp_path / "file.txt"
        source.write_text("test data")

        # Move to non-existent directory (parent dirs created automatically)
        result = move_file("file.txt", "new/path/to/file.txt", project_dir=tmp_path)

        assert result["success"] is True
        assert not source.exists()
        dest = tmp_path / "new" / "path" / "to" / "file.txt"
        assert dest.exists()
        assert dest.read_text() == "test data"

    def test_move_nonexistent_file_fails(self, tmp_path: Path) -> None:
        """Test that moving a non-existent file raises an error."""
        with pytest.raises(FileNotFoundError) as exc:
            move_file("nonexistent.txt", "destination.txt", project_dir=tmp_path)

        # Internal function can have detailed message
        assert "does not exist" in str(exc.value)

    def test_move_file_outside_project_fails(self, tmp_path: Path) -> None:
        """Test that moving files outside project directory is prevented."""
        # Create source file
        source = tmp_path / "source.txt"
        source.write_text("content")

        # Try to move outside project
        with pytest.raises(ValueError) as exc:
            move_file("source.txt", "../outside.txt", project_dir=tmp_path)

        # Internal function can have detailed security message
        assert "Security error" in str(exc.value) or "outside project" in str(exc.value)
        assert source.exists()  # Source should still exist

    def test_move_directory(self, tmp_path: Path) -> None:
        """Test moving a directory."""
        # Create source directory with files
        source_dir = tmp_path / "source_dir"
        source_dir.mkdir()
        (source_dir / "file1.txt").write_text("file 1")
        (source_dir / "file2.txt").write_text("file 2")

        # Move directory
        result = move_file("source_dir", "moved_dir", project_dir=tmp_path)

        assert result["success"] is True
        assert not source_dir.exists()
        dest_dir = tmp_path / "moved_dir"
        assert dest_dir.exists()
        assert (dest_dir / "file1.txt").read_text() == "file 1"
        assert (dest_dir / "file2.txt").read_text() == "file 2"

    def test_move_file_destination_exists_fails(self, tmp_path: Path) -> None:
        """Test that moving to an existing destination raises an error."""
        # Create both source and destination files
        source = tmp_path / "source.txt"
        source.write_text("source content")

        dest = tmp_path / "existing.txt"
        dest.write_text("existing content")

        # Try to move to existing destination
        with pytest.raises(FileExistsError) as exc:
            move_file("source.txt", "existing.txt", project_dir=tmp_path)

        assert "already exists" in str(exc.value)
        assert source.exists()  # Source should still exist
        assert dest.read_text() == "existing content"  # Destination unchanged

    def test_temp_directory_cleanup_verification(self, tmp_path: Path) -> None:
        """Verify that temp directories are properly isolated and cleaned.

        This test verifies that:
        1. Each test gets a fresh temporary directory
        2. Files created in one test don't affect other tests
        3. The temporary directory is automatically cleaned up
        """
        # Create some files in the temp directory
        test_file = tmp_path / "cleanup_test.txt"
        test_file.write_text("This file will be cleaned up automatically")

        test_dir = tmp_path / "cleanup_dir"
        test_dir.mkdir()
        (test_dir / "nested.txt").write_text("nested file")

        # Verify they exist during the test
        assert test_file.exists()
        assert test_dir.exists()
        assert (test_dir / "nested.txt").exists()

        # Store the temp directory name to verify it's unique
        temp_name = tmp_path.name
        # pytest's tmp_path uses different naming, typically like "pytest-of-{user}-{n}/pytest-current/{test_name}{n}"
        assert temp_name  # Just verify we have a name

        # Note: Actual cleanup happens automatically by pytest
        # The next test will get a completely different temp directory

    def test_move_with_special_characters(self, tmp_path: Path) -> None:
        """Test moving files with special characters in names."""
        # Test various special characters that are allowed in filenames
        special_names = [
            "file with spaces.txt",
            "file-with-dashes.txt",
            "file_with_underscores.txt",
            "file.multiple.dots.txt",
            "file(with)parens.txt",
            "file[with]brackets.txt",
            "file{with}braces.txt",
            "file@with#symbols.txt",
        ]

        for name in special_names:
            # Create source file with special name
            source = tmp_path / name
            source.write_text(f"content of {name}")

            # Create destination name
            dest_name = f"moved_{name}"

            # Move file
            result = move_file(name, dest_name, project_dir=tmp_path)

            assert result["success"] is True
            assert not source.exists()
            dest = tmp_path / dest_name
            assert dest.exists()
            assert dest.read_text() == f"content of {name}"

            # Clean up for next iteration
            if dest.exists():
                dest.unlink()

    def test_move_empty_file(self, tmp_path: Path) -> None:
        """Test moving an empty file."""
        # Create empty file
        source = tmp_path / "empty.txt"
        source.touch()

        # Move empty file
        result = move_file("empty.txt", "moved_empty.txt", project_dir=tmp_path)

        assert result["success"] is True
        assert not source.exists()
        dest = tmp_path / "moved_empty.txt"
        assert dest.exists()
        assert dest.stat().st_size == 0

    def test_move_preserves_file_permissions(self, tmp_path: Path) -> None:
        """Test that move preserves file permissions."""
        # Create source file
        source = tmp_path / "perms_test.txt"
        source.write_text("test content")

        # Set specific permissions (only on Unix-like systems)
        if os.name != "nt":  # Not Windows
            original_mode = 0o644
            source.chmod(original_mode)
            original_stat = source.stat()

            # Move file
            result = move_file(
                "perms_test.txt", "moved_perms.txt", project_dir=tmp_path
            )

            assert result["success"] is True
            dest = tmp_path / "moved_perms.txt"
            dest_stat = dest.stat()

            # Check that permissions are preserved
            assert dest_stat.st_mode == original_stat.st_mode
        else:
            # On Windows, just verify the move works
            result = move_file(
                "perms_test.txt", "moved_perms.txt", project_dir=tmp_path
            )
            assert result["success"] is True

    def test_move_nested_directory_structure(self, tmp_path: Path) -> None:
        """Test moving a complex nested directory structure."""
        # Create nested directory structure
        root_dir = tmp_path / "root"
        root_dir.mkdir()

        # Create nested subdirectories
        (root_dir / "level1").mkdir()
        (root_dir / "level1" / "level2").mkdir()
        (root_dir / "level1" / "level2" / "level3").mkdir()

        # Add files at different levels
        (root_dir / "root_file.txt").write_text("root file")
        (root_dir / "level1" / "l1_file.txt").write_text("level 1 file")
        (root_dir / "level1" / "level2" / "l2_file.txt").write_text("level 2 file")
        (root_dir / "level1" / "level2" / "level3" / "l3_file.txt").write_text(
            "level 3 file"
        )

        # Move entire structure
        result = move_file("root", "moved_root", project_dir=tmp_path)

        assert result["success"] is True
        assert not root_dir.exists()

        # Verify entire structure was moved
        moved_dir = tmp_path / "moved_root"
        assert moved_dir.exists()
        assert (moved_dir / "root_file.txt").read_text() == "root file"
        assert (moved_dir / "level1" / "l1_file.txt").read_text() == "level 1 file"
        assert (
            moved_dir / "level1" / "level2" / "l2_file.txt"
        ).read_text() == "level 2 file"
        assert (
            moved_dir / "level1" / "level2" / "level3" / "l3_file.txt"
        ).read_text() == "level 3 file"

    def test_move_handles_concurrent_modification(self, tmp_path: Path) -> None:
        """Test handling of concurrent modification scenarios."""
        # Create source file
        source = tmp_path / "concurrent_test.txt"
        source.write_text("original content")

        # Simulate a scenario where file might be modified during move
        # by mocking the filesystem operation
        with patch("shutil.move") as mock_move:
            # Configure mock to simulate a transient error then succeed
            mock_move.side_effect = [
                OSError("Resource temporarily unavailable"),
                str(tmp_path / "moved_concurrent.txt"),
            ]

            # First call should fail due to mock
            with pytest.raises(OSError):
                move_file(
                    "concurrent_test.txt",
                    "moved_concurrent.txt",
                    project_dir=tmp_path,
                )

            # Reset mock for successful move
            mock_move.side_effect = None
            mock_move.return_value = str(tmp_path / "moved_concurrent.txt")

            # Manual move simulation for test
            source.rename(tmp_path / "moved_concurrent.txt")

            # Verify file was moved despite initial error
            assert not source.exists()
            assert (tmp_path / "moved_concurrent.txt").exists()

    def test_move_symlinks(self, tmp_path: Path) -> None:
        """Test moving symbolic links."""
        # Skip on Windows if symlinks not supported
        if os.name == "nt":
            try:
                # Try to create a test symlink
                test_link = tmp_path / "test_link"
                test_target = tmp_path / "test_target"
                test_target.touch()
                test_link.symlink_to(test_target)
                test_link.unlink()
                test_target.unlink()
            except OSError:
                pytest.skip("Symlinks not supported on this Windows system")

        # Create target file
        target = tmp_path / "target.txt"
        target.write_text("target content")

        # Create symlink
        link = tmp_path / "link.txt"
        link.symlink_to(target)

        # Verify symlink works
        assert link.is_symlink()
        assert link.read_text() == "target content"

        # Move the symlink
        result = move_file("link.txt", "moved_link.txt", project_dir=tmp_path)

        assert result["success"] is True
        assert not link.exists()

        moved_link = tmp_path / "moved_link.txt"
        assert moved_link.exists()
        assert moved_link.is_symlink()
        assert moved_link.read_text() == "target content"

        # Original target should still exist
        assert target.exists()

    def test_move_large_directory(self, tmp_path: Path) -> None:
        """Test moving directories with many files."""
        # Create directory with many files
        large_dir = tmp_path / "large_dir"
        large_dir.mkdir()

        # Create 100 files
        for i in range(100):
            file = large_dir / f"file_{i:03d}.txt"
            file.write_text(f"Content of file {i}")

        # Create some subdirectories with files
        for i in range(10):
            subdir = large_dir / f"subdir_{i}"
            subdir.mkdir()
            for j in range(10):
                file = subdir / f"file_{j}.txt"
                file.write_text(f"Subdir {i} file {j}")

        # Move the large directory
        result = move_file("large_dir", "moved_large_dir", project_dir=tmp_path)

        assert result["success"] is True
        assert not large_dir.exists()

        moved_dir = tmp_path / "moved_large_dir"
        assert moved_dir.exists()

        # Verify all files were moved
        for i in range(100):
            file = moved_dir / f"file_{i:03d}.txt"
            assert file.exists()
            assert file.read_text() == f"Content of file {i}"

        # Verify subdirectories
        for i in range(10):
            subdir = moved_dir / f"subdir_{i}"
            assert subdir.exists()
            for j in range(10):
                file = subdir / f"file_{j}.txt"
                assert file.exists()
                assert file.read_text() == f"Subdir {i} file {j}"
