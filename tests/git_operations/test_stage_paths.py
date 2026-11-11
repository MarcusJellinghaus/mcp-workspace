"""Tests for list_untracked_paths and stage_paths."""

from pathlib import Path
from unittest.mock import patch

import pytest
from git import Repo

from mcp_workspace.git_operations.staging import list_untracked_paths, stage_paths


@pytest.mark.git_integration
class TestListUntrackedPaths:
    """Tests for list_untracked_paths."""

    def test_untracked_file_listed_tracked_modified_not(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """An untracked file is listed; a modified tracked file is not."""
        _, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("changed", encoding="utf-8")
        (project_dir / "new.txt").write_text("new", encoding="utf-8")

        result = list_untracked_paths([Path("README.md"), Path("new.txt")], project_dir)

        assert result == ["new.txt"]

    def test_directory_lists_nested_untracked_only(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A directory argument lists its untracked files, nested ones too."""
        repo, project_dir = git_repo_with_commit
        sub = project_dir / "sub"
        (sub / "deep").mkdir(parents=True)
        (sub / "tracked.txt").write_text("tracked", encoding="utf-8")
        repo.git.add("--", "sub/tracked.txt")
        repo.git.commit("-m", "Add tracked file")
        (sub / "tracked.txt").write_text("changed", encoding="utf-8")
        (sub / "a.txt").write_text("a", encoding="utf-8")
        (sub / "deep" / "b.txt").write_text("b", encoding="utf-8")

        result = list_untracked_paths([Path("sub")], project_dir)

        assert sorted(result) == ["sub/a.txt", "sub/deep/b.txt"]

    def test_gitignored_file_not_listed(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A gitignored file under the directory is not listed."""
        _, project_dir = git_repo_with_commit
        sub = project_dir / "sub"
        sub.mkdir()
        (sub / ".gitignore").write_text("*.log\n", encoding="utf-8")
        (sub / "keep.txt").write_text("keep", encoding="utf-8")
        (sub / "debug.log").write_text("log", encoding="utf-8")

        result = list_untracked_paths([Path("sub")], project_dir)

        assert sorted(result) == ["sub/.gitignore", "sub/keep.txt"]

    def test_star_path_is_literal(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """``x*.txt`` is matched literally and does not list ``xa.txt``."""
        _, project_dir = git_repo_with_commit
        (project_dir / "xa.txt").write_text("xa", encoding="utf-8")

        result = list_untracked_paths([Path("x*.txt")], project_dir)

        assert result == []

    def test_absolute_path(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """An absolute path inside project_dir is accepted."""
        _, project_dir = git_repo_with_commit
        (project_dir / "new.txt").write_text("new", encoding="utf-8")

        result = list_untracked_paths([project_dir / "new.txt"], project_dir)

        assert result == ["new.txt"]

    def test_non_ascii_path(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A non-ASCII untracked path is returned unquoted."""
        _, project_dir = git_repo_with_commit
        name = "üñíçødé_日本.txt"
        (project_dir / name).write_text("x", encoding="utf-8")

        result = list_untracked_paths([Path(name)], project_dir)

        assert result == [name]

    def test_path_outside_project(
        self, git_repo_with_commit: tuple[Repo, Path], tmp_path: Path
    ) -> None:
        """A path outside the repo returns an empty list."""
        _, project_dir = git_repo_with_commit
        outside = tmp_path / "outside.txt"
        outside.write_text("x", encoding="utf-8")

        assert list_untracked_paths([outside], project_dir) == []

    def test_empty_paths(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """An empty path list returns an empty list without running git."""
        _, project_dir = git_repo_with_commit
        (project_dir / "new.txt").write_text("new", encoding="utf-8")

        with patch(
            "mcp_workspace.git_operations.staging.run_git_raw"
        ) as mock_run_git_raw:
            result = list_untracked_paths([], project_dir)

        assert result == []
        mock_run_git_raw.assert_not_called()

    def test_non_repo(self, tmp_path: Path) -> None:
        """A non-repository directory returns an empty list."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        (plain_dir / "a.txt").write_text("a", encoding="utf-8")

        assert list_untracked_paths([Path("a.txt")], plain_dir) == []

    def test_git_failure(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A failing git call returns an empty list."""
        _, project_dir = git_repo_with_commit

        with patch(
            "mcp_workspace.git_operations.staging.run_git_raw",
            return_value=(128, b"new.txt\0", "fatal: boom"),
        ):
            result = list_untracked_paths([Path("new.txt")], project_dir)

        assert result == []


@pytest.mark.git_integration
class TestStagePaths:
    """Tests for stage_paths."""

    def test_stages_new_file(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A new file is staged as an addition."""
        repo, project_dir = git_repo_with_commit
        (project_dir / "new.txt").write_text("new", encoding="utf-8")

        result = stage_paths([Path("new.txt")], project_dir)

        assert result["success"] is True, result
        assert result["error"] is None
        assert result["returncode"] == 0
        assert repo.git.status("--porcelain", "--", "new.txt") == "A  new.txt"

    def test_empty_paths_is_success(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """An empty path list is a successful no-op without running git."""
        _, project_dir = git_repo_with_commit

        with patch(
            "mcp_workspace.git_operations.staging.run_git_raw"
        ) as mock_run_git_raw:
            result = stage_paths([], project_dir)

        assert result["success"] is True
        assert result["error"] is None
        assert result["returncode"] is None
        mock_run_git_raw.assert_not_called()

    def test_path_outside_project(
        self, git_repo_with_commit: tuple[Repo, Path], tmp_path: Path
    ) -> None:
        """A path outside project_dir is an error result without running git."""
        _, project_dir = git_repo_with_commit
        outside = tmp_path / "outside.txt"
        outside.write_text("x", encoding="utf-8")

        result = stage_paths([outside], project_dir)

        assert result["success"] is False
        assert result["error"] is not None
        assert result["returncode"] is None

    def test_git_failure_is_error_result(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A failing git add is reported with its exit code and stderr."""
        _, project_dir = git_repo_with_commit

        with patch(
            "mcp_workspace.git_operations.staging.run_git_raw",
            return_value=(128, b"", "fatal: index locked"),
        ):
            result = stage_paths([Path("new.txt")], project_dir)

        assert result["success"] is False
        assert result["error"] == "git add failed (exit 128)"
        assert result["returncode"] == 128
        assert result["stderr"] == "fatal: index locked"
