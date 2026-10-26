"""Tests for pull."""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.remotes import pull


def _clone_and_push(bare_remote_dir: Path, clone_dir: Path, filename: str) -> None:
    """Clone the bare remote, commit a new file and push it to main."""
    other = Repo.clone_from(str(bare_remote_dir), str(clone_dir), branch="main")
    try:
        with other.config_writer() as config:
            config.set_value("user", "name", "Other User")
            config.set_value("user", "email", "other@example.com")
            config.set_value("commit", "gpgsign", "false")
        (clone_dir / filename).write_text("from the other clone", encoding="utf-8")
        other.git.add(filename)
        other.git.commit("-m", f"Add {filename}")
        other.git.push("origin", "main")
    finally:
        other.close()


@pytest.mark.git_integration
class TestPull:
    """Tests for pull."""

    def test_fast_forward_pull(
        self, git_repo_with_remote: tuple[Repo, Path, Path], tmp_path: Path
    ) -> None:
        """A commit pushed from a second clone is pulled in."""
        repo, project_dir, bare_remote_dir = git_repo_with_remote
        repo.git.push("--set-upstream", "origin", "main")
        _clone_and_push(bare_remote_dir, tmp_path / "other", "new_file.txt")

        result = pull(project_dir)

        assert result["success"] is True
        assert result["error"] is None
        assert result["returncode"] == 0
        assert isinstance(result["stderr"], str)
        assert (project_dir / "new_file.txt").exists()

    def test_no_upstream(self, git_repo_with_remote: tuple[Repo, Path, Path]) -> None:
        """A branch without upstream is an error, decided before pulling."""
        _, project_dir, _ = git_repo_with_remote

        result = pull(project_dir)

        assert result["success"] is False
        assert result["error"] is not None
        assert "upstream" in result["error"]
        assert result["returncode"] not in (None, 0)
        assert result["stderr"]

    def test_detached_head_is_no_upstream(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """Detached HEAD is reported as no upstream."""
        repo, project_dir, _ = git_repo_with_remote
        repo.git.push("--set-upstream", "origin", "main")
        repo.git.checkout("--detach")

        result = pull(project_dir)

        assert result["success"] is False
        assert result["error"] is not None
        assert "upstream" in result["error"]

    def test_non_repo(self, tmp_path: Path) -> None:
        """A non-repository directory is an error result without a git process."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        result = pull(plain_dir)

        assert result["success"] is False
        assert result["error"]
        assert result["returncode"] is None
        assert result["stderr"] is None

    def test_missing_directory(self, tmp_path: Path) -> None:
        """A missing directory is an error result, not an exception."""
        result = pull(tmp_path / "does_not_exist")

        assert result["success"] is False
        assert result["returncode"] is None

    def test_pull_failure(
        self, git_repo_with_remote: tuple[Repo, Path, Path], tmp_path: Path
    ) -> None:
        """A pull that git rejects returns its nonzero exit code."""
        repo, project_dir, bare_remote_dir = git_repo_with_remote
        repo.git.push("--set-upstream", "origin", "main")
        bare_remote_dir.rename(tmp_path / "remote_gone.git")

        result = pull(project_dir)

        assert result["success"] is False
        assert result["error"] is not None
        assert "git pull failed" in result["error"]
        assert result["returncode"] not in (None, 0)
        assert result["stderr"]
