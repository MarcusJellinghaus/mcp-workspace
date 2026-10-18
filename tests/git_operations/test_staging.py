"""Minimal tests for git staging operations."""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.staging import (
    _chunk_paths,
    stage_all_changes,
    stage_specific_files,
)


def _enable_autocrlf_and_text_attr(
    repo: Repo, project_dir: Path, pattern: str = "*.md text"
) -> None:
    """Enable autocrlf and mark a pattern as text in .gitattributes."""
    with repo.config_writer() as config:
        config.set_value("core", "autocrlf", "true")
    (project_dir / ".gitattributes").write_text(pattern + "\n")


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

    def test_stage_specific_files_normalizes_crlf_for_new_file(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """New CRLF file is normalized to LF when staged, matching stage_all_changes."""
        repo, project_dir = git_repo_with_commit
        _enable_autocrlf_and_text_attr(repo, project_dir)

        file_path = project_dir / "doc.md"
        file_path.write_bytes(b"line one\r\nline two\r\n")

        result = stage_specific_files([file_path], project_dir)
        assert result is True

        blob_sha = repo.git.rev_parse(":doc.md")
        blob_content = repo.git.cat_file("blob", blob_sha, stdout_as_string=False)
        assert b"\r" not in blob_content

        # Unstage (index-only; working tree CRLF bytes untouched) and re-stage
        # the same untracked file via stage_all_changes for comparison.
        repo.git.reset("HEAD")
        result = stage_all_changes(project_dir)
        assert result is True

        other_blob_sha = repo.git.rev_parse(":doc.md")
        other_blob_content = repo.git.cat_file(
            "blob", other_blob_sha, stdout_as_string=False
        )
        assert blob_content == other_blob_content

    def test_stage_specific_files_matches_stage_all_for_modified_tracked_file(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Modifying a tracked file with CRLF stages identically via either path."""
        repo, project_dir = git_repo_with_commit
        _enable_autocrlf_and_text_attr(repo, project_dir)

        file_path = project_dir / "doc.md"
        file_path.write_bytes(b"line one\n")
        repo.index.add(["doc.md"])
        repo.index.commit("Add doc.md")

        file_path.write_bytes(b"line one\r\nline two\r\n")

        result = stage_specific_files([file_path], project_dir)
        assert result is True

        blob_sha = repo.git.rev_parse(":doc.md")
        blob_content = repo.git.cat_file("blob", blob_sha, stdout_as_string=False)
        assert b"\r" not in blob_content

        repo.git.reset("HEAD")
        result = stage_all_changes(project_dir)
        assert result is True

        other_blob_sha = repo.git.rev_parse(":doc.md")
        other_blob_content = repo.git.cat_file(
            "blob", other_blob_sha, stdout_as_string=False
        )
        assert blob_content == other_blob_content

    def test_stage_specific_files_literal_pathspec_bracket_filename(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A bracketed filename is staged literally, not as a glob pattern."""
        repo, project_dir = git_repo_with_commit

        bracket_file = project_dir / "a[1].md"
        bracket_file.write_text("bracket file")
        sibling_file = project_dir / "a1.md"
        sibling_file.write_text("sibling file")

        result = stage_specific_files([bracket_file], project_dir)
        assert result is True

        staged = [item.a_path for item in repo.index.diff("HEAD")]
        assert "a[1].md" in staged
        assert "a1.md" not in staged
        assert "a1.md" in repo.untracked_files

    def test_stage_specific_files_partial_staging_with_ignored_path(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A failing chunk still leaves the valid file staged (no all-or-nothing)."""
        repo, project_dir = git_repo_with_commit

        (project_dir / ".gitignore").write_text("ignored.py\n")

        normal_file = project_dir / "normal.py"
        normal_file.write_text("# normal")
        ignored_file = project_dir / "ignored.py"
        ignored_file.write_text("# ignored")

        result = stage_specific_files([normal_file, ignored_file], project_dir)
        assert result is False

        staged = [item.a_path for item in repo.index.diff("HEAD")]
        assert "normal.py" in staged
        assert "ignored.py" not in staged
