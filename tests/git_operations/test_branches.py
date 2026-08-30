"""Minimal tests for git branch mutation operations."""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.branch_queries import (
    branch_exists,
    get_current_branch_name,
)
from mcp_workspace.git_operations.branches import (
    checkout_branch,
    create_branch,
)
from mcp_workspace.git_operations.workflows import needs_rebase


@pytest.mark.git_integration
class TestBranchOperations:
    """Minimal tests for branch mutation operations - one test per function."""

    def test_create_and_branch_exists(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test create_branch and branch_exists work together."""
        _repo, project_dir = git_repo_with_commit

        # Create new branch (also checks it out)
        assert create_branch("feature-branch", project_dir) is True

        # Verify it exists
        assert branch_exists(project_dir, "feature-branch") is True
        assert branch_exists(project_dir, "nonexistent-branch") is False

    def test_checkout_branch_and_get_current(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test checkout_branch and get_current_branch_name work together."""
        _repo, project_dir = git_repo_with_commit

        # Create new branch (also checks it out)
        create_branch("feature-branch", project_dir)

        # Verify current branch (create_branch already checked it out)
        assert get_current_branch_name(project_dir) == "feature-branch"

    def test_checkout_branch_from_remote(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test checkout_branch can create local branch from remote."""
        repo, project_dir = git_repo_with_commit

        # Get initial branch
        initial_branch = get_current_branch_name(project_dir)
        assert initial_branch is not None

        # Create a test branch and commit
        create_branch("remote-test-branch", project_dir)
        (project_dir / "test_file.txt").write_text("test content")
        repo.index.add(["test_file.txt"])
        repo.index.commit("Test commit on remote-test-branch")

        # Push to remote (use bare repo as remote)
        # First ensure we have a remote (git_repo_with_commit should have one)
        if "origin" not in [remote.name for remote in repo.remotes]:
            pytest.skip("No origin remote configured")

        # Push the branch to remote
        repo.git.push("-u", "origin", "remote-test-branch")

        # Go back to initial branch and delete local copy
        checkout_branch(initial_branch, project_dir)
        repo.git.branch("-D", "remote-test-branch")

        # Verify branch doesn't exist locally
        assert branch_exists(project_dir, "remote-test-branch") is False

        # Checkout from remote - should create local tracking branch
        assert checkout_branch("remote-test-branch", project_dir) is True

        # Verify we're on the branch and it exists locally
        assert get_current_branch_name(project_dir) == "remote-test-branch"
        assert branch_exists(project_dir, "remote-test-branch") is True


@pytest.mark.git_integration
class TestNeedsRebase:
    """Test needs_rebase function for detecting when branches need rebasing."""

    def test_needs_rebase_up_to_date(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """Test needs_rebase returns False when branch is up-to-date."""
        repo, project_dir, _bare_remote = git_repo_with_remote

        # Push initial commit to remote
        repo.git.push("-u", "origin", "main")

        # Create feature branch from main
        create_branch("feature-branch", project_dir)

        # Branch should be up-to-date with main
        needs_rebase_result, reason = needs_rebase(project_dir, "main")
        assert needs_rebase_result is False
        assert reason == "up-to-date"

    def test_needs_rebase_behind(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """Test needs_rebase returns True when branch is behind target."""
        repo, project_dir, _bare_remote = git_repo_with_remote

        # Push initial commit to remote
        repo.git.push("-u", "origin", "main")

        # Create feature branch from main
        create_branch("feature-branch", project_dir)

        # Go back to main and make additional commits
        checkout_branch("main", project_dir)
        (project_dir / "new_file.txt").write_text("new content")
        repo.index.add(["new_file.txt"])
        repo.index.commit("New commit on main")

        # Push main updates to remote
        repo.git.push("origin", "main")

        # Switch back to feature branch
        checkout_branch("feature-branch", project_dir)

        # Feature branch should now be behind main
        needs_rebase_result, reason = needs_rebase(project_dir, "main")
        assert needs_rebase_result is True
        assert "behind" in reason

    def test_needs_rebase_invalid_repo(self, tmp_path: Path) -> None:
        """Test needs_rebase returns error for invalid repository."""
        # Create non-git directory
        non_git_dir = tmp_path / "not_a_repo"
        non_git_dir.mkdir()

        needs_rebase_result, reason = needs_rebase(non_git_dir, "main")
        assert needs_rebase_result is False
        assert reason.startswith("error:")
        assert "not a git repository" in reason.lower()

    def test_needs_rebase_no_remote(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Test needs_rebase handles repo with no remote gracefully."""
        _repo, project_dir = git_repo_with_commit

        # Create feature branch
        create_branch("feature-branch", project_dir)

        # Should handle no remote gracefully
        needs_rebase_result, reason = needs_rebase(project_dir, "main")
        assert needs_rebase_result is False
        assert "error:" in reason
        assert "remote" in reason.lower()

    def test_needs_rebase_auto_detect_target(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """Test needs_rebase can auto-detect target branch when not specified."""
        repo, project_dir, _bare_remote = git_repo_with_remote

        # Push initial commit to remote
        repo.git.push("-u", "origin", "main")

        # Create feature branch
        create_branch("feature-branch", project_dir)

        # Should auto-detect main as target branch
        needs_rebase_result, reason = needs_rebase(project_dir)
        assert needs_rebase_result is False
        assert reason == "up-to-date"

    def test_needs_rebase_nonexistent_target(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """Test needs_rebase handles nonexistent target branch."""
        repo, project_dir, _bare_remote = git_repo_with_remote

        # Push initial commit to remote
        repo.git.push("-u", "origin", "main")

        # Create feature branch
        create_branch("feature-branch", project_dir)

        # Try to check against nonexistent branch
        needs_rebase_result, reason = needs_rebase(project_dir, "nonexistent")
        assert needs_rebase_result is False
        assert "error:" in reason
        assert "does not exist" in reason.lower() or "not found" in reason.lower()

    def test_needs_rebase_on_default_branch_behind_origin(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """A stale local 'main' reports its real behind-count."""
        repo, project_dir, _bare_remote = git_repo_with_remote

        sha_a = str(repo.head.commit.hexsha)
        repo.git.push("-u", "origin", "main")

        (project_dir / "new_file.txt").write_text("new content")
        repo.index.add(["new_file.txt"])
        repo.index.commit("New commit on main")
        repo.git.push("origin", "main")  # origin/main is now ahead by one

        repo.git.reset("--hard", sha_a)  # local main falls behind

        needs_rebase_result, reason = needs_rebase(project_dir, "main")
        assert needs_rebase_result is True
        assert reason == "1 commit behind"

    def test_needs_rebase_current_branch_never_pushed(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """No origin/<current branch> means up-to-date, not an error."""
        _repo, project_dir, _bare_remote = git_repo_with_remote

        # 'main' exists locally only; the bare origin has no refs at all.
        needs_rebase_result, reason = needs_rebase(project_dir, "main")
        assert needs_rebase_result is False
        assert reason == "up-to-date"
