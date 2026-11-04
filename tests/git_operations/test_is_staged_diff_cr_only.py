"""Tests for is_staged_diff_cr_only."""

from pathlib import Path
from unittest.mock import patch

import pytest
from git import Repo

from mcp_workspace.git_operations.repository_status import is_staged_diff_cr_only
from mcp_workspace.git_operations.staging import renormalize_paths


@pytest.mark.git_integration
class TestIsStagedDiffCrOnly:
    """Tests for is_staged_diff_cr_only."""

    def test_crlf_only_change(self, crlf_repo: tuple[Repo, Path]) -> None:
        """A renormalized CRLF-only change is CR-only."""
        _, project_dir = crlf_repo
        assert renormalize_paths([Path("doc.md")], project_dir)["success"] is True

        assert is_staged_diff_cr_only([Path("doc.md")], project_dir) is True

    def test_content_change(self, crlf_repo: tuple[Repo, Path]) -> None:
        """An added line is not CR-only."""
        _, project_dir = crlf_repo
        (project_dir / "doc.md").write_bytes(
            b"line one\r\n    indented\r\nnew line\r\n"
        )
        assert renormalize_paths([Path("doc.md")], project_dir)["success"] is True

        assert is_staged_diff_cr_only([Path("doc.md")], project_dir) is False

    def test_indentation_change(self, crlf_repo: tuple[Repo, Path]) -> None:
        """A whitespace-only change is not CR-only (guards against ``-w``)."""
        _, project_dir = crlf_repo
        (project_dir / "doc.md").write_bytes(b"line one\r\n  indented\r\n")
        assert renormalize_paths([Path("doc.md")], project_dir)["success"] is True

        assert is_staged_diff_cr_only([Path("doc.md")], project_dir) is False

    def test_empty_paths(self, crlf_repo: tuple[Repo, Path]) -> None:
        """An empty list is True; git without a pathspec would see .gitattributes."""
        repo, project_dir = crlf_repo
        repo.git.add(".gitattributes")

        assert is_staged_diff_cr_only([], project_dir) is True

    @pytest.mark.parametrize("paths", [[], [Path("a.md")]])
    def test_non_repo(self, tmp_path: Path, paths: list[Path]) -> None:
        """A non-repository directory is False."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        assert is_staged_diff_cr_only(paths, plain_dir) is False

    def test_path_outside_project(
        self, crlf_repo: tuple[Repo, Path], tmp_path: Path
    ) -> None:
        """A path outside project_dir is False."""
        _, project_dir = crlf_repo
        outside = tmp_path / "outside.md"
        outside.write_text("x", encoding="utf-8")

        assert is_staged_diff_cr_only([outside], project_dir) is False

    def test_second_chunk_not_cr_only(self, crlf_repo: tuple[Repo, Path]) -> None:
        """A real change in the second chunk is False after a CR-only first chunk."""
        repo, project_dir = crlf_repo
        (project_dir / "other.md").write_bytes(b"new file\n")
        repo.git.add("--", "other.md")
        assert renormalize_paths([Path("doc.md")], project_dir)["success"] is True

        with patch(
            "mcp_workspace.git_operations.repository_status._chunk_paths",
            side_effect=lambda paths: [[p] for p in paths],
        ) as mock_chunk:
            result = is_staged_diff_cr_only(
                [Path("doc.md"), Path("other.md")], project_dir
            )

        mock_chunk.assert_called_once_with(["doc.md", "other.md"])
        assert result is False
        assert is_staged_diff_cr_only([Path("doc.md")], project_dir) is True
