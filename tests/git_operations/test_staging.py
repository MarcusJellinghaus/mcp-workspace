"""Minimal tests for git staging operations."""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.staging import (
    _chunk_paths,
    stage_all_changes,
    stage_specific_files,
)


class TestChunkPaths:
    """Unit tests for the pure `_chunk_paths` helper."""

    def test_empty_list_returns_empty_list(self) -> None:
        """Empty input yields no chunks, not a single empty chunk."""
        assert _chunk_paths([]) == []

    def test_short_paths_fit_in_one_chunk(self) -> None:
        """Paths well under max_chars stay together, in order."""
        paths = ["a.py", "b.py", "c.py"]
        assert _chunk_paths(paths, max_chars=100) == [paths]

    def test_running_total_crosses_limit_splits_into_chunks(self) -> None:
        """When the running total would exceed max_chars, a new chunk starts."""
        paths = ["aaaaa", "bbbbb", "ccccc", "ddddd"]
        # "aaaaa bbbbb" = 11 chars fits in max_chars=11; adding "ccccc" (+1) would
        # exceed it, so it starts a new chunk.
        result = _chunk_paths(paths, max_chars=11)
        assert result == [["aaaaa", "bbbbb"], ["ccccc", "ddddd"]]
        # Every path present exactly once, in order.
        assert [p for chunk in result for p in chunk] == paths

    def test_oversized_path_gets_its_own_chunk(self) -> None:
        """A single path longer than max_chars is never dropped or merged."""
        long_path = "x" * 50
        paths = ["short1", long_path, "short2"]
        result = _chunk_paths(paths, max_chars=10)
        assert long_path in [chunk[0] for chunk in result if len(chunk) == 1]
        assert [p for chunk in result for p in chunk] == paths
        for chunk in result:
            if long_path in chunk:
                assert chunk == [long_path]


@pytest.mark.git_integration
class TestStagingOperations:
    """Minimal tests for staging operations - one test per function."""

    def test_stage_all_changes(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """Test stage_all_changes stages all files."""
        repo, project_dir = git_repo_with_commit

        # Create multiple files
        file1 = project_dir / "file1.py"
        file1.write_text("# File 1")
        file2 = project_dir / "file2.py"
        file2.write_text("# File 2")

        # Stage all changes
        result = stage_all_changes(project_dir)

        assert result is True

        # Verify files are staged
        staged = [item.a_path for item in repo.index.diff("HEAD")]
        assert "file1.py" in staged
        assert "file2.py" in staged

    def test_stage_specific_files(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test stage_specific_files stages only specified files."""
        repo, project_dir = git_repo_with_commit

        # Create multiple files
        file1 = project_dir / "file1.py"
        file1.write_text("# File 1")
        file2 = project_dir / "file2.py"
        file2.write_text("# File 2")
        file3 = project_dir / "file3.py"
        file3.write_text("# File 3")

        # Stage only specific files
        result = stage_specific_files([file1, file2], project_dir)

        assert result is True

        # Verify only specified files are staged
        staged = [item.a_path for item in repo.index.diff("HEAD")]
        assert "file1.py" in staged
        assert "file2.py" in staged

        # file3.py should still be untracked
        assert "file3.py" in repo.untracked_files
