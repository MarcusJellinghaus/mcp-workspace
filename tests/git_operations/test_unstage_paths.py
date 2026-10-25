"""Tests for unstage_paths."""

from pathlib import Path
from unittest.mock import patch

import pytest
from git import Repo

from mcp_workspace.git_operations.staging import unstage_paths


def _commit_files(repo: Repo, project_dir: Path, files: dict[str, str]) -> None:
    """Write files and commit them in one commit."""
    for name, content in files.items():
        (project_dir / name).write_text(content, encoding="utf-8")
        repo.git.add("--", name)
    repo.git.commit("-m", "Add files")


def _staged_files(repo: Repo) -> set[str]:
    """Return paths with staged changes (works on an unborn HEAD)."""
    head_rc = repo.git.rev_parse(
        "--verify", "-q", "HEAD", with_exceptions=False, with_extended_output=True
    )[0]
    if head_rc == 0:
        out = repo.git.diff("--cached", "--name-only", "-z", stdout_as_string=False)
    else:
        # Unborn HEAD: every index entry is a staged addition
        out = repo.git.ls_files("-z", stdout_as_string=False)
    return {p for p in out.decode("utf-8").split("\0") if p}


def _untracked_files(repo: Repo) -> set[str]:
    """Return untracked paths."""
    out = repo.git.ls_files(
        "--others", "--exclude-standard", "-z", stdout_as_string=False
    )
    return {p for p in out.decode("utf-8").split("\0") if p}


def _stage_index_only(repo: Repo, project_dir: Path, name: str) -> None:
    """Stage ``name`` as a new index entry without a file on disk.

    Lets tests use names such as ``x*.txt`` that Windows cannot create.
    Git for Windows rejects such index paths unless ``core.protectNTFS`` is off.
    """
    repo.git.config("core.protectNTFS", "false")
    blob_source = project_dir / "blob_source.tmp"
    blob_source.write_text("content", encoding="utf-8")
    sha = repo.git.hash_object("-w", str(blob_source))
    blob_source.unlink()
    repo.git.update_index("--add", "--cacheinfo", f"100644,{sha},{name}")


@pytest.mark.git_integration
class TestUnstagePaths:
    """Tests for unstage_paths."""

    def test_unstages_modification_keeps_content(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A staged modification is unstaged; the working tree is untouched."""
        repo, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("changed", encoding="utf-8")
        repo.git.add("--", "README.md")

        result = unstage_paths([Path("README.md")], project_dir)

        assert result["success"] is True, result
        assert result["error"] is None
        assert result["returncode"] == 0
        assert _staged_files(repo) == set()
        assert (project_dir / "README.md").read_text(encoding="utf-8") == "changed"

    def test_absolute_path(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """An absolute path inside project_dir is accepted."""
        repo, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("changed", encoding="utf-8")
        repo.git.add("--", "README.md")

        result = unstage_paths([project_dir / "README.md"], project_dir)

        assert result["success"] is True
        assert _staged_files(repo) == set()

    def test_unborn_head(self, git_repo: tuple[Repo, Path]) -> None:
        """On an unborn HEAD a staged new file becomes untracked."""
        repo, project_dir = git_repo
        (project_dir / "first.txt").write_text("first", encoding="utf-8")
        repo.git.add("--", "first.txt")

        result = unstage_paths([Path("first.txt")], project_dir)

        assert result["success"] is True, result
        assert _staged_files(repo) == set()
        assert _untracked_files(repo) == {"first.txt"}
        assert (project_dir / "first.txt").exists()

    def test_idempotent(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """Unstaging twice succeeds both times."""
        repo, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("changed", encoding="utf-8")
        repo.git.add("--", "README.md")

        first = unstage_paths([Path("README.md")], project_dir)
        second = unstage_paths([Path("README.md")], project_dir)

        assert first["success"] is True
        assert second["success"] is True
        assert _staged_files(repo) == set()

    def test_idempotent_unborn_head(self, git_repo: tuple[Repo, Path]) -> None:
        """Unstaging twice on an unborn HEAD succeeds both times."""
        repo, project_dir = git_repo
        (project_dir / "first.txt").write_text("first", encoding="utf-8")
        repo.git.add("--", "first.txt")

        first = unstage_paths([Path("first.txt")], project_dir)
        second = unstage_paths([Path("first.txt")], project_dir)

        assert first["success"] is True
        assert second["success"] is True, second

    def test_empty_paths_is_success(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """An empty path list is a successful no-op without running git."""
        repo, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("changed", encoding="utf-8")
        repo.git.add("--", "README.md")

        with patch(
            "mcp_workspace.git_operations.staging.run_git_raw"
        ) as mock_run_git_raw:
            result = unstage_paths([], project_dir)

        assert result["success"] is True
        assert result["error"] is None
        mock_run_git_raw.assert_not_called()
        assert _staged_files(repo) == {"README.md"}

    def test_star_path_is_literal(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """``x*.txt`` is unstaged literally; ``xa.txt`` stays staged."""
        repo, project_dir = git_repo_with_commit
        _stage_index_only(repo, project_dir, "x*.txt")
        (project_dir / "xa.txt").write_text("xa", encoding="utf-8")
        repo.git.add("--", "xa.txt")

        result = unstage_paths([Path("x*.txt")], project_dir)

        assert result["success"] is True, result
        assert _staged_files(repo) == {"xa.txt"}

    def test_magic_pathspec_is_literal(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A magic pathspec matches nothing; ``a.txt`` stays staged."""
        repo, project_dir = git_repo_with_commit
        (project_dir / "a.txt").write_text("a", encoding="utf-8")
        repo.git.add("--", "a.txt")

        result = unstage_paths([Path(":(glob)*.txt")], project_dir)

        assert result["success"] is True, result
        assert _staged_files(repo) == {"a.txt"}

    def test_non_ascii_path(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A non-ASCII path is unstaged."""
        repo, project_dir = git_repo_with_commit
        name = "üñíçødé_日本.txt"
        _commit_files(repo, project_dir, {name: "one"})
        (project_dir / name).write_text("two", encoding="utf-8")
        repo.git.add("--", name)

        result = unstage_paths([Path(name)], project_dir)

        assert result["success"] is True, result
        assert _staged_files(repo) == set()

    def test_path_outside_project(
        self, git_repo_with_commit: tuple[Repo, Path], tmp_path: Path
    ) -> None:
        """A path outside project_dir is an error result without running git."""
        _, project_dir = git_repo_with_commit
        outside = tmp_path / "outside.txt"
        outside.write_text("x", encoding="utf-8")

        result = unstage_paths([outside], project_dir)

        assert result["success"] is False
        assert result["error"] is not None
        assert result["returncode"] is None
        assert result["stderr"] is None

    def test_non_repo(self, tmp_path: Path) -> None:
        """A non-repository directory is an error result, not an exception."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        result = unstage_paths([Path("a.txt")], plain_dir)

        assert result["success"] is False
        assert result["error"] is not None
        assert result["returncode"] is None

    def test_chunks_paths(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """Each chunk is unstaged when the path list is split."""
        repo, project_dir = git_repo_with_commit
        _commit_files(repo, project_dir, {"a.txt": "a", "b.txt": "b"})
        for name in ("a.txt", "b.txt"):
            (project_dir / name).write_text(f"{name}2", encoding="utf-8")
            repo.git.add("--", name)

        with patch(
            "mcp_workspace.git_operations.staging._chunk_paths",
            side_effect=lambda paths: [[p] for p in paths],
        ) as mock_chunk:
            result = unstage_paths([Path("a.txt"), Path("b.txt")], project_dir)

        assert result["success"] is True, result
        mock_chunk.assert_called_once_with(["a.txt", "b.txt"])
        assert _staged_files(repo) == set()

    def test_git_failure_is_error_result(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A failing git call is reported with its exit code and stderr."""
        _, project_dir = git_repo_with_commit
        responses = [(0, b"", ""), (128, b"", "fatal: index locked")]

        with patch(
            "mcp_workspace.git_operations.staging.run_git_raw",
            side_effect=responses,
        ):
            result = unstage_paths([Path("README.md")], project_dir)

        assert result["success"] is False
        assert result["error"] is not None
        assert result["returncode"] == 128
        assert result["stderr"] == "fatal: index locked"
