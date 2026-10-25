"""Tests for get_working_tree_status."""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.repository_status import get_working_tree_status


@pytest.mark.git_integration
class TestGetWorkingTreeStatus:
    """Tests for get_working_tree_status."""

    def test_clean_repo(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A freshly committed repo is clean."""
        _, project_dir = git_repo_with_commit

        result = get_working_tree_status(project_dir)

        assert result["success"] is True, result
        assert result["error"] is None
        assert result["returncode"] == 0
        assert result["clean"] is True
        assert result["staged"] == []
        assert result["modified"] == []
        assert result["untracked"] == []

    def test_buckets(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """Staged, modified and untracked files land in their own bucket."""
        repo, project_dir = git_repo_with_commit
        (project_dir / "tracked.txt").write_text("one", encoding="utf-8")
        repo.git.add("--", "tracked.txt")
        repo.git.commit("-m", "Add tracked")
        (project_dir / "staged.txt").write_text("staged", encoding="utf-8")
        repo.git.add("--", "staged.txt")
        (project_dir / "tracked.txt").write_text("two", encoding="utf-8")
        (project_dir / "untracked.txt").write_text("new", encoding="utf-8")

        result = get_working_tree_status(project_dir)

        assert result["success"] is True, result
        assert result["clean"] is False
        assert result["staged"] == ["staged.txt"]
        assert result["modified"] == ["tracked.txt"]
        assert result["untracked"] == ["untracked.txt"]

    def test_staged_and_modified_same_file(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A file staged and then changed again is in both buckets."""
        repo, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("staged", encoding="utf-8")
        repo.git.add("--", "README.md")
        (project_dir / "README.md").write_text("modified again", encoding="utf-8")

        result = get_working_tree_status(project_dir)

        assert result["staged"] == ["README.md"]
        assert result["modified"] == ["README.md"]
        assert result["clean"] is False

    def test_non_ascii_name(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A non-ASCII file name round-trips unquoted."""
        _, project_dir = git_repo_with_commit
        name = "üñíçødé_日本.txt"
        (project_dir / name).write_text("x", encoding="utf-8")

        result = get_working_tree_status(project_dir)

        assert result["success"] is True, result
        assert result["untracked"] == [name]

    def test_untracked_dir_listed_per_file(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Files in a new directory are listed individually with ``/``."""
        _, project_dir = git_repo_with_commit
        new_dir = project_dir / "new_dir" / "sub"
        new_dir.mkdir(parents=True)
        (new_dir / "a.txt").write_text("a", encoding="utf-8")
        (new_dir / "b.txt").write_text("b", encoding="utf-8")

        result = get_working_tree_status(project_dir)

        assert sorted(result["untracked"]) == [
            "new_dir/sub/a.txt",
            "new_dir/sub/b.txt",
        ]

    def test_corrupt_index(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A corrupt index is a failure and never reports clean."""
        repo, project_dir = git_repo_with_commit
        Path(repo.git_dir, "index").write_bytes(b"garbage, not an index")

        result = get_working_tree_status(project_dir)

        assert result["success"] is False
        assert result["clean"] is False
        assert result["error"] is not None
        assert result["returncode"] not in (None, 0)
        assert result["staged"] == []
        assert result["modified"] == []
        assert result["untracked"] == []

    def test_non_repo(self, tmp_path: Path) -> None:
        """A non-repository is a failure result, not an exception."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        result = get_working_tree_status(plain_dir)

        assert result["success"] is False
        assert result["clean"] is False
        assert result["error"] is not None
        assert result["returncode"] is None
        assert result["stderr"] is None
        assert result["staged"] == []
