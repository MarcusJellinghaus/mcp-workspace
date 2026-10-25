"""Tests for conflict inspection (list_unmerged_paths)."""

from pathlib import Path
from typing import Callable
from unittest.mock import patch

import pytest
from git import Repo
from git.exc import GitCommandError

from mcp_workspace.git_operations import list_unmerged_paths, rebase_start
from tests.git_operations.conftest import FileChanges

BuildRepo = Callable[[FileChanges, FileChanges, FileChanges], tuple[Repo, Path]]

RUNNER = "mcp_workspace.git_operations.conflicts.run_git_raw"


class TestListUnmergedPaths:
    """list_unmerged_paths outcomes."""

    def test_no_conflict(self, make_conflict_repo: BuildRepo) -> None:
        """Nothing unmerged -> empty list."""
        _, project_dir = make_conflict_repo(
            {"a.txt": "base\n"}, {"a.txt": "main\n"}, {"a.txt": "feature\n"}
        )

        assert not list_unmerged_paths(project_dir)

    def test_two_conflicted_files(self, make_conflict_repo: BuildRepo) -> None:
        """Each conflicted path is listed once, in git's order."""
        _, project_dir = make_conflict_repo(
            {"a.txt": "base\n", "dätei.txt": "base\n"},
            {"a.txt": "main\n", "dätei.txt": "main\n"},
            {"a.txt": "feature\n", "dätei.txt": "feature\n"},
        )
        assert rebase_start(project_dir, "main")["status"] == "stopped_on_conflict"

        assert list_unmerged_paths(project_dir) == ["a.txt", "dätei.txt"]

    def test_non_repo_raises(self, tmp_path: Path) -> None:
        """A non-repository raises ValueError."""
        with pytest.raises(ValueError):
            list_unmerged_paths(tmp_path)

    def test_git_failure_raises(self, git_repo: tuple[Repo, Path]) -> None:
        """A nonzero exit raises GitCommandError."""
        _, project_dir = git_repo

        with patch(RUNNER, return_value=(128, b"", "fatal")):
            with pytest.raises(GitCommandError):
                list_unmerged_paths(project_dir)
