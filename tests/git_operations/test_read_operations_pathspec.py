"""Integration tests for pathspec auto-split behavior in read operations."""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.read_operations import git_diff


@pytest.mark.git_integration
class TestPathspecAutoSplit:
    """Auto-split '--' from args into pathspec for pathspec commands."""

    def test_diff_double_dash_in_args_equivalent_to_pathspec(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        repo, project_dir = git_repo_with_commit
        (project_dir / "a.txt").write_text("changed")
        repo.index.add(["a.txt"])
        repo.index.commit("change a")

        via_dashes = git_diff(project_dir, args=["HEAD~1", "HEAD", "--", "a.txt"])
        via_pathspec = git_diff(
            project_dir, args=["HEAD~1", "HEAD"], pathspec=["a.txt"]
        )
        assert via_dashes == via_pathspec

    def test_diff_rejects_double_dash_with_explicit_pathspec(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with pytest.raises(ValueError, match="either '--' in args or the 'pathspec'"):
            git_diff(
                project_dir,
                args=["HEAD", "--", "a.txt"],
                pathspec=["b.txt"],
            )
