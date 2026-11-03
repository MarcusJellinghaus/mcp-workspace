"""Tests for renormalize_paths."""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.repository_status import get_working_tree_status
from mcp_workspace.git_operations.staging import renormalize_paths


@pytest.mark.git_integration
class TestRenormalizePaths:
    """Tests for renormalize_paths."""

    def test_crlf_only_change_is_staged(self, crlf_repo: tuple[Repo, Path]) -> None:
        """A CRLF-only file is staged and no longer shows as modified."""
        _, project_dir = crlf_repo

        result = renormalize_paths([Path("doc.md")], project_dir)

        assert result["success"] is True, result
        assert result["error"] is None
        status = get_working_tree_status(project_dir)
        assert "doc.md" in status["staged"]
        assert "doc.md" not in status["modified"]

    def test_deleted_tracked_path_fails(self, crlf_repo: tuple[Repo, Path]) -> None:
        """A deleted tracked path makes git exit 128."""
        _, project_dir = crlf_repo
        (project_dir / "doc.md").unlink()

        result = renormalize_paths([Path("doc.md")], project_dir)

        assert result["success"] is False
        assert result["error"] is not None
        assert result["returncode"] == 128
        assert result["stderr"]

    def test_untracked_path_stages_nothing(self, crlf_repo: tuple[Repo, Path]) -> None:
        """An untracked path is a success that stages nothing."""
        _, project_dir = crlf_repo
        (project_dir / "new.md").write_bytes(b"new\r\n")

        result = renormalize_paths([Path("new.md")], project_dir)

        assert result["success"] is True, result
        status = get_working_tree_status(project_dir)
        assert status["staged"] == []
        assert "new.md" in status["untracked"]

    def test_empty_paths_stages_nothing(self, crlf_repo: tuple[Repo, Path]) -> None:
        """An empty list is a success; git without a pathspec would stage doc.md."""
        _, project_dir = crlf_repo

        result = renormalize_paths([], project_dir)

        assert result["success"] is True
        assert result["error"] is None
        assert get_working_tree_status(project_dir)["staged"] == []

    @pytest.mark.parametrize("paths", [[], [Path("a.md")]])
    def test_non_repo(self, tmp_path: Path, paths: list[Path]) -> None:
        """A non-repository directory is an error result, not an exception."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        result = renormalize_paths(paths, plain_dir)

        assert result["success"] is False
        assert result["error"] is not None
        assert result["returncode"] is None
        assert result["stderr"] is None

    def test_path_outside_project(
        self, crlf_repo: tuple[Repo, Path], tmp_path: Path
    ) -> None:
        """A path outside project_dir is an error result without running git."""
        _, project_dir = crlf_repo
        outside = tmp_path / "outside.md"
        outside.write_text("x", encoding="utf-8")

        result = renormalize_paths([outside], project_dir)

        assert result["success"] is False
        assert result["error"] is not None
        assert result["returncode"] is None
