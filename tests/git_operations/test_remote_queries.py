"""Tests for probe_origin_branch and the origin_has_branch wrapper."""

from pathlib import Path

import pytest
from git import Repo
from git.exc import GitCommandError

from mcp_workspace.git_operations.base_branch import origin_has_branch
from mcp_workspace.git_operations.remotes import probe_origin_branch


@pytest.mark.git_integration
class TestProbeOriginBranch:
    """Tests for probe_origin_branch."""

    def test_pushed_branch_exists(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """A branch pushed to origin is reported as existing."""
        repo, project_dir, _ = git_repo_with_remote
        repo.git.push("origin", "main")

        result = probe_origin_branch(project_dir, "main")

        assert result["success"] is True
        assert result["exists"] is True
        assert result["error"] is None
        assert result["returncode"] == 0

    def test_absent_branch(self, git_repo_with_remote: tuple[Repo, Path, Path]) -> None:
        """A branch origin does not have is a successful 'absent' answer."""
        repo, project_dir, _ = git_repo_with_remote
        repo.git.push("origin", "main")

        result = probe_origin_branch(project_dir, "no-such-branch")

        assert result["success"] is True
        assert result["exists"] is False
        assert result["error"] is None

    def test_fresh_clone_sees_branch_pushed_later(
        self, git_repo_with_remote: tuple[Repo, Path, Path], tmp_path: Path
    ) -> None:
        """Origin is asked directly; no local origin/<branch> is needed."""
        repo, _, bare_remote_dir = git_repo_with_remote
        repo.git.push("origin", "main")
        clone_dir = tmp_path / "clone"
        Repo.clone_from(str(bare_remote_dir), str(clone_dir)).close()
        repo.git.branch("later")
        repo.git.push("origin", "later")

        result = probe_origin_branch(clone_dir, "later")

        assert result["success"] is True
        assert result["exists"] is True

    def test_full_ref_does_not_match_suffix(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """'team/main' on origin does not count as 'main'."""
        repo, project_dir, _ = git_repo_with_remote
        repo.git.push("origin", "main:team/main")

        result = probe_origin_branch(project_dir, "main")

        assert result["success"] is True
        assert result["exists"] is False

    def test_unreachable_remote(
        self, git_repo_with_remote: tuple[Repo, Path, Path], tmp_path: Path
    ) -> None:
        """An unreachable origin can't answer: exists is None."""
        repo, project_dir, _ = git_repo_with_remote
        repo.git.remote("set-url", "origin", str(tmp_path / "missing.git"))

        result = probe_origin_branch(project_dir, "main")

        assert result["success"] is False
        assert result["exists"] is None
        assert result["error"]
        assert result["returncode"] not in (None, 0)
        assert result["stderr"]

    def test_blank_branch(self, git_repo_with_remote: tuple[Repo, Path, Path]) -> None:
        """A blank branch name is an error result without a git process."""
        _, project_dir, _ = git_repo_with_remote

        result = probe_origin_branch(project_dir, "  ")

        assert result["success"] is False
        assert result["exists"] is None
        assert result["error"]
        assert result["returncode"] is None
        assert result["stderr"] is None

    def test_non_repo(self, tmp_path: Path) -> None:
        """A non-repository is an error result without a git process."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        result = probe_origin_branch(plain_dir, "main")

        assert result["success"] is False
        assert result["exists"] is None
        assert result["returncode"] is None
        assert result["stderr"] is None


@pytest.mark.git_integration
class TestOriginHasBranchWrapper:
    """Tests for origin_has_branch over probe_origin_branch."""

    def test_returns_exists(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """True for a pushed branch, False for an absent one."""
        repo, project_dir, _ = git_repo_with_remote
        repo.git.push("origin", "main")

        assert origin_has_branch(project_dir, "main") is True
        assert origin_has_branch(project_dir, "gone") is False

    def test_unreachable_remote_raises(
        self, git_repo_with_remote: tuple[Repo, Path, Path], tmp_path: Path
    ) -> None:
        """Origin that can't answer raises GitCommandError."""
        repo, project_dir, _ = git_repo_with_remote
        repo.git.remote("set-url", "origin", str(tmp_path / "missing.git"))

        with pytest.raises(GitCommandError):
            origin_has_branch(project_dir, "main")
