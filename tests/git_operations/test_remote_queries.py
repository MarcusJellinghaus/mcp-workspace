"""Tests for origin queries: probe_origin_branch, list_remote_branches."""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.remotes import (
    list_remote_branches,
    probe_origin_branch,
)


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
class TestListRemoteBranches:
    """Tests for list_remote_branches."""

    def test_many_branches_not_truncated(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """All 120 heads on origin are returned."""
        repo, project_dir, _ = git_repo_with_remote
        head_sha = repo.git.rev_parse("HEAD")
        expected = {f"feature-{i:03d}" for i in range(119)} | {"main"}
        for name in expected - {"main"}:
            repo.git.update_ref(f"refs/heads/{name}", head_sha)
        repo.git.push("--all", "origin")

        result = list_remote_branches(project_dir)

        assert result["success"] is True
        assert result["error"] is None
        assert result["returncode"] == 0
        assert len(result["branches"]) == 120
        assert set(result["branches"]) == expected

    def test_only_main(self, git_repo_with_remote: tuple[Repo, Path, Path]) -> None:
        """A remote holding only main lists only main."""
        repo, project_dir, _ = git_repo_with_remote
        repo.git.push("origin", "main")

        result = list_remote_branches(project_dir)

        assert result["success"] is True
        assert result["branches"] == ["main"]

    def test_empty_remote(self, git_repo_with_remote: tuple[Repo, Path, Path]) -> None:
        """A bare remote with nothing pushed is a successful empty list."""
        _, project_dir, _ = git_repo_with_remote

        result = list_remote_branches(project_dir)

        assert result["success"] is True
        assert result["error"] is None
        assert result["branches"] == []

    def test_unreachable_remote(
        self, git_repo_with_remote: tuple[Repo, Path, Path], tmp_path: Path
    ) -> None:
        """An unreachable origin is a failure, never a successful empty list."""
        repo, project_dir, _ = git_repo_with_remote
        repo.git.remote("set-url", "origin", str(tmp_path / "missing.git"))

        result = list_remote_branches(project_dir)

        assert result["success"] is False
        assert result["branches"] == []
        assert result["error"]
        assert result["returncode"] not in (None, 0)
        assert result["stderr"]

    def test_non_repo(self, tmp_path: Path) -> None:
        """A non-repository is an error result without a git process."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        result = list_remote_branches(plain_dir)

        assert result["success"] is False
        assert result["branches"] == []
        assert result["error"]
        assert result["returncode"] is None
        assert result["stderr"] is None
