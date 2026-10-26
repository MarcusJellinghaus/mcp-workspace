"""Tests for the shared git runner and helpers in core.py."""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.core import (
    GIT_NONINTERACTIVE_ENV,
    is_option_like,
    open_repo_for_query,
    run_git_raw,
    to_git_paths,
)


@pytest.mark.git_integration
class TestRunGitRaw:
    """Tests for run_git_raw."""

    def test_nonzero_exit_returned_not_raised(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A failing git command returns its exit code and str stderr."""
        repo, _ = git_repo_with_commit

        returncode, stdout, stderr = run_git_raw(repo, "rev_parse", "--verify", "nope")

        assert returncode != 0
        assert isinstance(stdout, bytes)
        assert isinstance(stderr, str)
        assert stderr

    def test_success_returns_zero_and_bytes(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A successful command returns 0 and stdout bytes."""
        repo, _ = git_repo_with_commit

        returncode, stdout, stderr = run_git_raw(repo, "rev_parse", "HEAD")

        assert returncode == 0
        assert isinstance(stdout, bytes)
        assert len(stdout) == 40
        assert isinstance(stderr, str)

    def test_non_ascii_file_name_round_trips(self, git_repo: tuple[Repo, Path]) -> None:
        """ls-files -z output is raw UTF-8 bytes for non-ASCII names."""
        repo, project_dir = git_repo
        name = "über_файл.txt"
        (project_dir / name).write_text("x", encoding="utf-8")
        repo.git.add("--", name)

        returncode, stdout, _ = run_git_raw(repo, "ls_files", "-z")

        assert returncode == 0
        entries = [e for e in stdout.split(b"\0") if e]
        assert entries == [name.encode("utf-8")]

    def test_strip_newline_false_keeps_trailing_newline(
        self, git_repo: tuple[Repo, Path]
    ) -> None:
        """strip_newline=False keeps blob content byte-exact; default strips."""
        repo, project_dir = git_repo
        (project_dir / "f.txt").write_bytes(b"line\n")
        repo.git.add("--", "f.txt")
        sha = repo.git.rev_parse(":f.txt")

        _, kept, _ = run_git_raw(repo, "cat_file", "blob", sha, strip_newline=False)
        _, stripped, _ = run_git_raw(repo, "cat_file", "blob", sha)

        assert kept == b"line\n"
        assert stripped == b"line"

    def test_env_is_applied(self, git_repo: tuple[Repo, Path]) -> None:
        """The per-call env reaches the git process."""
        repo, _ = git_repo

        returncode, stdout, _ = run_git_raw(
            repo, "var", "GIT_EDITOR", env=GIT_NONINTERACTIVE_ENV
        )

        assert returncode == 0
        assert stdout == b"true"

    def test_literal_paths_treats_glob_literally(
        self, git_repo: tuple[Repo, Path]
    ) -> None:
        """literal_paths=True matches '*.txt' only as a literal file name."""
        repo, project_dir = git_repo
        (project_dir / "a.txt").write_text("a")
        repo.git.add("--", "a.txt")
        # Windows forbids '*' in file names, so add the entry to the index only;
        # Git for Windows also rejects such index paths unless protectNTFS is off.
        repo.git.config("core.protectNTFS", "false")
        blob = repo.git.hash_object("-w", "a.txt")
        repo.git.update_index("--add", "--cacheinfo", f"100644,{blob},*.txt")

        _, literal, _ = run_git_raw(
            repo, "ls_files", "-z", "--", "*.txt", literal_paths=True
        )
        _, globbed, _ = run_git_raw(repo, "ls_files", "-z", "--", "*.txt")

        assert [e for e in literal.split(b"\0") if e] == [b"*.txt"]
        assert sorted(e for e in globbed.split(b"\0") if e) == [b"*.txt", b"a.txt"]

    def test_literal_paths_disables_magic_pathspec(
        self, git_repo: tuple[Repo, Path]
    ) -> None:
        """literal_paths=True makes ':(glob)' an ordinary (non-matching) path."""
        repo, project_dir = git_repo
        (project_dir / "a.txt").write_text("a")
        repo.git.add("--", "a.txt")

        _, literal, _ = run_git_raw(
            repo, "ls_files", "-z", "--", ":(glob)*.txt", literal_paths=True
        )
        _, magic, _ = run_git_raw(repo, "ls_files", "-z", "--", ":(glob)*.txt")

        assert literal == b""
        assert [e for e in magic.split(b"\0") if e] == [b"a.txt"]


class TestIsOptionLike:
    """Tests for is_option_like."""

    @pytest.mark.parametrize("value", ["-x", "--force", "-"])
    def test_option_like(self, value: str) -> None:
        """Values starting with '-' are option-like."""
        assert is_option_like(value) is True

    @pytest.mark.parametrize("value", ["main", "origin/main", "abc123", "a-b", ""])
    def test_not_option_like(self, value: str) -> None:
        """Values not starting with '-' are not option-like."""
        assert is_option_like(value) is False


class TestToGitPaths:
    """Tests for to_git_paths."""

    def test_relative_path(self, tmp_path: Path) -> None:
        """Relative paths are resolved against project_dir."""
        assert to_git_paths([Path("src/a.py")], tmp_path) == ["src/a.py"]

    def test_absolute_path(self, tmp_path: Path) -> None:
        """Absolute paths inside project_dir become repo-relative."""
        assert to_git_paths([tmp_path / "src" / "a.py"], tmp_path) == ["src/a.py"]

    def test_windows_backslashes_become_forward_slashes(self, tmp_path: Path) -> None:
        """Nested paths always use forward slashes."""
        nested = Path("dir") / "sub" / "file.txt"
        assert to_git_paths([nested], tmp_path) == ["dir/sub/file.txt"]

    def test_multiple_paths_keep_order(self, tmp_path: Path) -> None:
        """Order of the input is preserved."""
        result = to_git_paths([Path("b.txt"), tmp_path / "a.txt"], tmp_path)
        assert result == ["b.txt", "a.txt"]

    def test_outside_project_raises(self, tmp_path: Path) -> None:
        """A path outside project_dir raises ValueError."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        with pytest.raises(ValueError):
            to_git_paths([tmp_path / "other.txt"], project_dir)

    def test_relative_escape_raises(self, tmp_path: Path) -> None:
        """A relative path escaping project_dir via '..' raises ValueError."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        with pytest.raises(ValueError):
            to_git_paths([Path("..") / "other.txt"], project_dir)

    def test_symlink_is_not_followed(self, tmp_path: Path) -> None:
        """A symlink keeps its own path, whether its target is inside or outside."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (tmp_path / "outside.txt").write_text("o", encoding="utf-8")
        (project_dir / "inside.txt").write_text("i", encoding="utf-8")
        try:
            (project_dir / "out_link").symlink_to(tmp_path / "outside.txt")
            (project_dir / "in_link").symlink_to(project_dir / "inside.txt")
        except OSError:
            pytest.skip("Creating symlinks is not possible on this platform")

        result = to_git_paths([Path("out_link"), project_dir / "in_link"], project_dir)

        assert result == ["out_link", "in_link"]


@pytest.mark.git_integration
class TestOpenRepoForQuery:
    """Tests for open_repo_for_query."""

    def test_yields_repo(self, git_repo: tuple[Repo, Path]) -> None:
        """A valid repository is yielded."""
        _, project_dir = git_repo
        with open_repo_for_query(project_dir) as repo:
            assert Path(repo.working_dir).resolve() == project_dir.resolve()

    def test_plain_directory_raises_value_error(self, tmp_path: Path) -> None:
        """A directory that is not a repository raises ValueError."""
        with pytest.raises(ValueError):
            with open_repo_for_query(tmp_path):
                pass

    def test_missing_directory_raises_value_error(self, tmp_path: Path) -> None:
        """A missing directory raises ValueError."""
        with pytest.raises(ValueError):
            with open_repo_for_query(tmp_path / "missing"):
                pass
