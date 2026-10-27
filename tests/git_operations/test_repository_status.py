"""Tests for repository status operations."""

from pathlib import Path
from unittest.mock import patch

import pytest
from git import Repo
from git.exc import GitCommandError

from mcp_workspace.git_operations.repository_status import (
    get_full_status,
    is_git_repository,
    is_working_directory_clean,
)


@pytest.mark.git_integration
class TestRepositoryReaders:
    """Tests for repository status reader functions."""

    def test_is_git_repository(
        self, git_repo: tuple[Repo, Path], tmp_path: Path
    ) -> None:
        """Test is_git_repository detects git repos."""
        _repo, project_dir = git_repo

        # Should detect git repo
        assert is_git_repository(project_dir) is True

        # Should not detect non-git directory
        non_git_dir = tmp_path / "not_a_repo"
        non_git_dir.mkdir()
        assert is_git_repository(non_git_dir) is False

    def test_is_working_directory_clean(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test is_working_directory_clean detects changes."""
        _repo, project_dir = git_repo_with_commit

        # Clean working directory
        assert is_working_directory_clean(project_dir) is True

        # Add untracked file
        new_file = project_dir / "new.py"
        new_file.write_text("# New file")
        assert is_working_directory_clean(project_dir) is False

    def test_get_full_status(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """Test get_full_status returns complete status."""
        repo, project_dir = git_repo_with_commit

        # Create staged, modified, and untracked files
        staged_file = project_dir / "staged.py"
        staged_file.write_text("# Staged")
        repo.index.add(["staged.py"])

        modified_file = project_dir / "README.md"
        modified_file.write_text("# Modified")

        untracked_file = project_dir / "untracked.py"
        untracked_file.write_text("# Untracked")

        # Get full status
        status = get_full_status(project_dir)

        assert "staged" in status
        assert "modified" in status
        assert "untracked" in status
        assert any("staged.py" in f for f in status["staged"])
        assert any("README.md" in f for f in status["modified"])
        assert any("untracked.py" in f for f in status["untracked"])

    def test_is_working_directory_clean_ignore_files_none(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test ignore_files=None preserves existing behavior."""
        _repo, project_dir = git_repo_with_commit

        # Create untracked file
        new_file = project_dir / "new.txt"
        new_file.write_text("new content")

        # Should return False - untracked file detected
        assert is_working_directory_clean(project_dir, ignore_files=None) is False

    def test_is_working_directory_clean_ignore_files_empty_list(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test ignore_files=[] behaves same as None (backward compatibility)."""
        _repo, project_dir = git_repo_with_commit

        # Create untracked file
        new_file = project_dir / "new.txt"
        new_file.write_text("new content")

        # Should return False - empty list should not filter anything
        assert is_working_directory_clean(project_dir, ignore_files=[]) is False

    def test_is_working_directory_clean_ignore_files_matches_untracked(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test ignore_files filters matching untracked file."""
        _repo, project_dir = git_repo_with_commit

        # Create untracked file that should be ignored
        uv_lock = project_dir / "uv.lock"
        uv_lock.write_text("lock content")

        # Should return True - uv.lock is ignored, directory is clean
        assert is_working_directory_clean(project_dir, ignore_files=["uv.lock"]) is True

    def test_is_working_directory_clean_ignore_files_other_untracked(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test ignore_files does not filter non-matching files."""
        _repo, project_dir = git_repo_with_commit

        # Create untracked file that does NOT match ignore_files
        other_file = project_dir / "other.txt"
        other_file.write_text("other content")

        # Should return False - other.txt is not ignored
        assert (
            is_working_directory_clean(project_dir, ignore_files=["uv.lock"]) is False
        )

    def test_is_working_directory_clean_ignore_files_with_other_changes(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test ignore_files with matching file AND other changes."""
        _repo, project_dir = git_repo_with_commit

        # Create ignored file AND another untracked file
        uv_lock = project_dir / "uv.lock"
        uv_lock.write_text("lock content")

        real_change = project_dir / "real_change.txt"
        real_change.write_text("real change content")

        # Should return False - real_change.txt is still detected
        assert (
            is_working_directory_clean(project_dir, ignore_files=["uv.lock"]) is False
        )


@pytest.mark.git_integration
class TestGetFullStatusParity:
    """get_full_status matches git's porcelain status on real repositories."""

    def test_staged(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A newly staged file is listed under staged only."""
        repo, project_dir = git_repo_with_commit
        (project_dir / "f.py").write_text("# f")
        repo.git.add("f.py")

        result = get_full_status(project_dir)

        assert set(result) == {"staged", "modified", "untracked"}
        assert result == {"staged": ["f.py"], "modified": [], "untracked": []}

    def test_modified(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """An edited tracked file is listed under modified only."""
        _repo, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("# Modified")

        assert get_full_status(project_dir) == {
            "staged": [],
            "modified": ["README.md"],
            "untracked": [],
        }

    def test_untracked_in_new_dir(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """An untracked file in a new directory is listed by its own path."""
        _repo, project_dir = git_repo_with_commit
        (project_dir / "d").mkdir()
        (project_dir / "d" / "x.py").write_text("# x")

        assert get_full_status(project_dir) == {
            "staged": [],
            "modified": [],
            "untracked": ["d/x.py"],
        }

    def test_staged_then_modified(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A file staged and edited again is both staged and modified."""
        repo, project_dir = git_repo_with_commit
        (project_dir / "f.py").write_text("# f")
        repo.git.add("f.py")
        (project_dir / "f.py").write_text("# f changed")

        assert get_full_status(project_dir) == {
            "staged": ["f.py"],
            "modified": ["f.py"],
            "untracked": [],
        }

    def test_rename(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A staged rename is listed under its new path."""
        repo, project_dir = git_repo_with_commit
        repo.git.mv("README.md", "docs.md")

        assert get_full_status(project_dir) == {
            "staged": ["docs.md"],
            "modified": [],
            "untracked": [],
        }

    def test_rename_then_modify(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A renamed-then-edited file is listed by its new path in both lists."""
        repo, project_dir = git_repo_with_commit
        repo.git.mv("README.md", "docs.md")
        (project_dir / "docs.md").write_text("# Changed after rename")

        assert get_full_status(project_dir) == {
            "staged": ["docs.md"],
            "modified": ["docs.md"],
            "untracked": [],
        }

    def test_non_ascii(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A non-ASCII path is returned raw, not C-quoted."""
        _repo, project_dir = git_repo_with_commit
        (project_dir / "ä.txt").write_text("umlaut", encoding="utf-8")

        assert get_full_status(project_dir) == {
            "staged": [],
            "modified": [],
            "untracked": ["ä.txt"],
        }

    def test_unborn_head(self, git_repo: tuple[Repo, Path]) -> None:
        """A file staged before the first commit is listed under staged."""
        repo, project_dir = git_repo
        (project_dir / "f.py").write_text("# f")
        repo.git.add("f.py")

        assert get_full_status(project_dir) == {
            "staged": ["f.py"],
            "modified": [],
            "untracked": [],
        }

    def test_unmerged(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A conflicted (UU) file is both staged and modified."""
        repo, project_dir = git_repo_with_commit
        base = repo.active_branch.name
        readme = project_dir / "README.md"

        repo.git.checkout("-b", "other")
        readme.write_text("# Other side")
        repo.git.commit("-am", "other")
        repo.git.checkout(base)
        readme.write_text("# Base side")
        repo.git.commit("-am", "base")
        with pytest.raises(GitCommandError):
            repo.git.merge("other")

        assert get_full_status(project_dir) == {
            "staged": ["README.md"],
            "modified": ["README.md"],
            "untracked": [],
        }

    def test_intent_to_add(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """An intent-to-add file is modified, not staged."""
        repo, project_dir = git_repo_with_commit
        (project_dir / "f.py").write_text("# f")
        repo.git.add("-N", "f.py")

        assert get_full_status(project_dir) == {
            "staged": [],
            "modified": ["f.py"],
            "untracked": [],
        }

    def test_not_a_repo(self, tmp_path: Path) -> None:
        """A plain directory gives all-empty lists."""
        plain = tmp_path / "plain"
        plain.mkdir()

        assert get_full_status(plain) == {
            "staged": [],
            "modified": [],
            "untracked": [],
        }

    def test_status_raises(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """An exception from the status read gives all-empty lists."""
        _repo, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("# Modified")

        with patch(
            "mcp_workspace.git_operations.repository_status.get_working_tree_status",
            side_effect=RuntimeError("boom"),
        ):
            result = get_full_status(project_dir)

        assert result == {"staged": [], "modified": [], "untracked": []}
