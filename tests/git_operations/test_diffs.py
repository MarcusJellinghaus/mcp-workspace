"""Minimal tests for git diff operations."""

import logging
from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.branch_queries import (
    branch_exists,
    get_current_branch_name,
)
from mcp_workspace.git_operations.branches import (
    create_branch,
)
from mcp_workspace.git_operations.diffs import (
    get_branch_diff,
    get_git_diff_for_commit,
)
from mcp_workspace.git_operations.workflows import commit_all_changes


@pytest.mark.git_integration
class TestDiffOperations:
    """Minimal tests for diff operations - one test per function."""

    def test_get_git_diff_for_commit(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test get_git_diff_for_commit returns diff for staged/unstaged changes."""
        _repo, project_dir = git_repo_with_commit

        # Create a new file (unstaged)
        test_file = project_dir / "test.py"
        test_file.write_text("# Test file\ndef hello():\n    print('Hello')")

        # Get diff for current changes
        diff = get_git_diff_for_commit(project_dir)

        assert diff is not None
        assert "test.py" in diff
        assert "def hello():" in diff

    def test_get_branch_diff(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """Test get_branch_diff returns diff between branches."""
        _repo, project_dir = git_repo_with_commit

        # Get base branch name
        base_branch = get_current_branch_name(project_dir)

        # Create feature branch and make changes
        create_branch("feature-branch", project_dir)

        # Add file on feature branch
        feature_file = project_dir / "feature.py"
        feature_file.write_text("# Feature file")
        commit_all_changes("Add feature file", project_dir)

        # Get diff between branches
        diff = get_branch_diff(project_dir, base_branch)

        assert diff != ""
        assert "feature.py" in diff
        assert "# Feature file" in diff

    def test_get_branch_diff_with_base_branch(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test get_branch_diff with explicit base branch."""
        _repo, project_dir = git_repo_with_commit

        # Get current branch name
        base_branch = get_current_branch_name(project_dir)

        # Create feature branch (also checks it out)
        create_branch("feature", project_dir)

        # Add file
        feature_file = project_dir / "feature.py"
        feature_file.write_text("# Feature")
        commit_all_changes("Add feature", project_dir)

        # Get diff with explicit base branch
        diff = get_branch_diff(project_dir, base_branch=base_branch)

        assert diff != ""
        assert "feature.py" in diff

    def test_get_branch_diff_falls_back_to_remote(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """Test get_branch_diff falls back to remote ref when local branch missing."""
        repo, project_dir, _ = git_repo_with_remote

        # Get initial branch name (main)
        initial_branch = get_current_branch_name(project_dir)
        assert initial_branch is not None

        # Push main to remote
        repo.git.push("-u", "origin", initial_branch)

        # Create feature branch with changes
        create_branch("feature-branch", project_dir)
        feature_file = project_dir / "feature.py"
        feature_file.write_text("# Feature file")
        commit_all_changes("Add feature file", project_dir)

        # Delete local main branch (simulating CI environment)
        repo.git.branch("-D", initial_branch)

        # Verify local main doesn't exist
        assert branch_exists(project_dir, initial_branch) is False

        # get_branch_diff should still work using origin/main
        diff = get_branch_diff(project_dir, initial_branch)

        assert diff != ""
        assert "feature.py" in diff
        assert "# Feature file" in diff

    def test_get_branch_diff_returns_empty_when_no_base_branch(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """get_branch_diff returns empty string when base_branch is None."""
        _, project_dir = git_repo_with_commit

        result = get_branch_diff(project_dir, base_branch=None)

        assert result == ""

    def test_get_branch_diff_logs_error_when_no_base_branch(
        self, git_repo_with_commit: tuple[Repo, Path], caplog: pytest.LogCaptureFixture
    ) -> None:
        """get_branch_diff logs error when base_branch is None."""
        _, project_dir = git_repo_with_commit

        with caplog.at_level(logging.ERROR):
            result = get_branch_diff(project_dir, base_branch=None)

        assert result == ""
        assert "base_branch is required" in caplog.text

    def test_get_branch_diff_ansi_false_returns_plain_text(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Default ansi=False returns a string without ANSI escape codes."""
        _repo, project_dir = git_repo_with_commit

        base_branch = get_current_branch_name(project_dir)
        create_branch("feature-ansi-false", project_dir)

        feature_file = project_dir / "ansi_test.py"
        feature_file.write_text("# ansi test")
        commit_all_changes("Add ansi test file", project_dir)

        diff = get_branch_diff(project_dir, base_branch)
        assert "\x1b[" not in diff

    def test_get_branch_diff_ansi_parameter_accepted(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """ansi=True is accepted without error (smoke test — ANSI may or may not
        appear depending on git/terminal, but the call must not raise)."""
        _repo, project_dir = git_repo_with_commit

        base_branch = get_current_branch_name(project_dir)
        create_branch("feature-ansi-true", project_dir)

        feature_file = project_dir / "ansi_test2.py"
        feature_file.write_text("# ansi test 2")
        commit_all_changes("Add ansi test 2 file", project_dir)

        diff = get_branch_diff(project_dir, base_branch, ansi=True)
        assert isinstance(diff, str)
