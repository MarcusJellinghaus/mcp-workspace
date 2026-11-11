"""Tests for committed_files."""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.commits import committed_files

from .conftest import commit_files


@pytest.mark.git_integration
class TestCommittedFiles:
    """Tests for committed_files."""

    def test_root_commit_lists_all_files(self, git_repo: tuple[Repo, Path]) -> None:
        """A root commit with two files lists both."""
        repo, project_dir = git_repo
        commit_files(repo, {"a.txt": "a", "sub/b.txt": "b"}, "root")

        assert sorted(committed_files(project_dir)) == ["a.txt", "sub/b.txt"]

    def test_added_modified_deleted_all_listed(
        self, git_repo: tuple[Repo, Path]
    ) -> None:
        """A commit adding, modifying and deleting one file each lists all three."""
        repo, project_dir = git_repo
        commit_files(repo, {"keep.txt": "v1", "gone.txt": "bye"}, "base")
        commit_files(
            repo,
            {"new.txt": "new", "keep.txt": "v2", "gone.txt": None},
            "change",
        )

        assert sorted(committed_files(project_dir)) == [
            "gone.txt",
            "keep.txt",
            "new.txt",
        ]

    def test_explicit_rev(self, git_repo: tuple[Repo, Path]) -> None:
        """An explicit rev reports that commit, not HEAD."""
        repo, project_dir = git_repo
        first = commit_files(repo, {"first.txt": "1"}, "first")
        commit_files(repo, {"second.txt": "2"}, "second")

        assert committed_files(project_dir, first) == ["first.txt"]

    def test_option_like_rev_returns_empty(self, git_repo: tuple[Repo, Path]) -> None:
        """A rev starting with ``-`` is refused."""
        repo, project_dir = git_repo
        commit_files(repo, {"a.txt": "a"}, "root")

        assert committed_files(project_dir, "--all") == []

    def test_unknown_rev_returns_empty(self, git_repo: tuple[Repo, Path]) -> None:
        """A rev git cannot resolve yields an empty list."""
        repo, project_dir = git_repo
        commit_files(repo, {"a.txt": "a"}, "root")

        assert committed_files(project_dir, "no-such-ref") == []

    def test_non_repository_returns_empty(self, tmp_path: Path) -> None:
        """A directory that is not a repository yields an empty list."""
        assert committed_files(tmp_path) == []
