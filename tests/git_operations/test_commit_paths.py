"""Tests for commit_paths."""

from pathlib import Path
from unittest.mock import patch

import pytest
from git import Repo

from mcp_workspace.git_operations.commits import commit_paths


def _commit_files(repo: Repo, project_dir: Path, files: dict[str, str]) -> None:
    """Write files and commit them in one commit."""
    for name, content in files.items():
        (project_dir / name).write_text(content, encoding="utf-8")
        repo.git.add("--", name)
    repo.git.commit("-m", "Add files")


def _head_files(repo: Repo) -> set[str]:
    """Return the paths changed by HEAD."""
    out = repo.git.show(
        "--name-only", "-z", "--format=", "HEAD", stdout_as_string=False
    )
    return {p for p in out.decode("utf-8").split("\0") if p}


def _unstaged_files(repo: Repo) -> set[str]:
    """Return paths with unstaged working-tree changes."""
    out = repo.git.diff("--name-only", "-z", stdout_as_string=False)
    return {p for p in out.decode("utf-8").split("\0") if p}


def _staged_files(repo: Repo) -> set[str]:
    """Return paths with staged changes."""
    out = repo.git.diff("--cached", "--name-only", "-z", stdout_as_string=False)
    return {p for p in out.decode("utf-8").split("\0") if p}


@pytest.mark.git_integration
class TestCommitPaths:
    """Tests for commit_paths."""

    def test_commits_only_given_path(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Only the given path is committed; other changes stay uncommitted."""
        repo, project_dir = git_repo_with_commit
        _commit_files(repo, project_dir, {"a.txt": "a", "b.txt": "b", "c.txt": "c"})
        (project_dir / "a.txt").write_text("a2", encoding="utf-8")
        (project_dir / "b.txt").write_text("b2", encoding="utf-8")
        (project_dir / "c.txt").write_text("c2", encoding="utf-8")
        repo.git.add("--", "c.txt")

        result = commit_paths("Commit a", [Path("a.txt")], project_dir)

        assert result["success"] is True
        assert result["error"] is None
        assert result["error_category"] is None
        assert result["returncode"] == 0
        assert result["commit_hash"] is not None
        assert len(result["commit_hash"]) == 7
        assert repo.git.rev_parse("HEAD").startswith(result["commit_hash"])
        assert _head_files(repo) == {"a.txt"}
        assert _unstaged_files(repo) == {"b.txt"}
        assert _staged_files(repo) == {"c.txt"}

    def test_absolute_path(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """An absolute path inside project_dir is accepted."""
        repo, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("changed", encoding="utf-8")

        result = commit_paths("Update", [project_dir / "README.md"], project_dir)

        assert result["success"] is True
        assert _head_files(repo) == {"README.md"}

    def test_unmodified_path_is_nothing_to_commit(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """An unmodified tracked path has nothing to commit."""
        _, project_dir = git_repo_with_commit

        result = commit_paths("Nothing", [Path("README.md")], project_dir)

        assert result["success"] is False
        assert result["error"] == "Nothing to commit for the given paths"
        assert result["error_category"] == "nothing_to_commit"
        assert result["commit_hash"] is None

    def test_missing_path_is_nothing_to_commit(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A path that is neither tracked nor on disk has nothing to commit."""
        _, project_dir = git_repo_with_commit

        result = commit_paths("Nothing", [Path("ghost.txt")], project_dir)

        assert result["error_category"] == "nothing_to_commit"

    def test_untracked_path_is_validation_failed(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """An untracked path is rejected."""
        _, project_dir = git_repo_with_commit
        (project_dir / "new.txt").write_text("new", encoding="utf-8")

        result = commit_paths("Add new", [Path("new.txt")], project_dir)

        assert result["success"] is False
        assert result["error_category"] == "validation_failed"
        assert result["error"] is not None
        assert "new.txt" in result["error"]

    def test_path_outside_project_is_validation_failed(
        self, git_repo_with_commit: tuple[Repo, Path], tmp_path: Path
    ) -> None:
        """A path outside project_dir is rejected without running git."""
        _, project_dir = git_repo_with_commit
        outside = tmp_path / "outside.txt"
        outside.write_text("x", encoding="utf-8")

        result = commit_paths("Outside", [outside], project_dir)

        assert result["success"] is False
        assert result["error_category"] == "validation_failed"
        assert result["returncode"] is None

    @pytest.mark.parametrize("message", ["", "   \n"])
    def test_empty_message_is_validation_failed(
        self, git_repo_with_commit: tuple[Repo, Path], message: str
    ) -> None:
        """An empty or whitespace-only message is rejected."""
        _, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("changed", encoding="utf-8")

        result = commit_paths(message, [Path("README.md")], project_dir)

        assert result["success"] is False
        assert result["error_category"] == "validation_failed"

    def test_empty_paths_is_validation_failed(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """An empty path list is rejected."""
        _, project_dir = git_repo_with_commit

        result = commit_paths("Message", [], project_dir)

        assert result["success"] is False
        assert result["error_category"] == "validation_failed"

    def test_non_repo_is_validation_failed(self, tmp_path: Path) -> None:
        """A non-repository directory is an error result, not an exception."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        result = commit_paths("Message", [Path("a.txt")], plain_dir)

        assert result["success"] is False
        assert result["error_category"] == "validation_failed"
        assert result["returncode"] is None

    def test_non_ascii_path_and_message(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Non-ASCII file names and messages round-trip."""
        repo, project_dir = git_repo_with_commit
        name = "üñíçødé_日本.txt"
        _commit_files(repo, project_dir, {name: "one"})
        (project_dir / name).write_text("two", encoding="utf-8")
        message = "Änderung: 日本語のメッセージ"

        result = commit_paths(message, [Path(name)], project_dir)

        assert result["success"] is True
        assert _head_files(repo) == {name}
        subject = repo.git.log("-1", "--format=%s", stdout_as_string=False)
        assert subject.decode("utf-8").strip() == message

    def test_bracket_path_is_literal(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """``a[1].txt`` is committed literally, not as a glob matching ``a1.txt``."""
        repo, project_dir = git_repo_with_commit
        _commit_files(repo, project_dir, {"a[1].txt": "x", "a1.txt": "y"})
        (project_dir / "a[1].txt").write_text("x2", encoding="utf-8")
        (project_dir / "a1.txt").write_text("y2", encoding="utf-8")

        result = commit_paths("Bracket", [Path("a[1].txt")], project_dir)

        assert result["success"] is True
        assert _head_files(repo) == {"a[1].txt"}
        assert _unstaged_files(repo) == {"a1.txt"}

    def test_magic_pathspec_is_literal(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A magic pathspec is matched literally and selects nothing."""
        repo, project_dir = git_repo_with_commit
        _commit_files(repo, project_dir, {"a.txt": "a"})
        (project_dir / "a.txt").write_text("a2", encoding="utf-8")

        result = commit_paths("Magic", [Path(":(glob)*.txt")], project_dir)

        assert result["success"] is False
        assert result["error_category"] == "nothing_to_commit"
        assert _unstaged_files(repo) == {"a.txt"}

    def test_tracked_symlink_to_outside(
        self,
        git_repo_with_commit: tuple[Repo, Path],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """A tracked symlink pointing outside the repo is committed as itself."""
        repo, project_dir = git_repo_with_commit
        outside = tmp_path_factory.mktemp("outside")
        link = project_dir / "link"
        try:
            link.symlink_to(outside / "one.txt")
        except OSError:
            pytest.skip("Creating symlinks is not possible on this platform")
        repo.git.config("core.symlinks", "true")
        repo.git.add("--", "link")
        repo.git.commit("-m", "Add link")
        link.unlink()
        link.symlink_to(outside / "two.txt")

        result = commit_paths("Retarget link", [Path("link")], project_dir)

        assert result["success"] is True, result
        assert _head_files(repo) == {"link"}

    def test_unborn_head(self, git_repo: tuple[Repo, Path]) -> None:
        """A staged new file is committed on an unborn HEAD."""
        repo, project_dir = git_repo
        (project_dir / "first.txt").write_text("first", encoding="utf-8")
        repo.git.add("--", "first.txt")

        result = commit_paths("First", [Path("first.txt")], project_dir)

        assert result["success"] is True, result
        assert result["commit_hash"] is not None
        assert _head_files(repo) == {"first.txt"}

    def test_signing_failure_classified(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A commit whose stderr mentions gpg is a signing failure."""
        _, project_dir = git_repo_with_commit
        responses = [
            (0, b" M README.md\0", ""),
            (128, b"", "error: gpg failed to sign the data"),
        ]

        with patch(
            "mcp_workspace.git_operations.commits.run_git_raw",
            side_effect=responses,
        ):
            result = commit_paths("Signed", [Path("README.md")], project_dir)

        assert result["success"] is False
        assert result["error_category"] == "signing_failed"
        assert result["returncode"] == 128
        assert result["stderr"] == "error: gpg failed to sign the data"

    def test_other_commit_failure_classified(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A commit failing for another reason is a commit failure."""
        _, project_dir = git_repo_with_commit
        responses = [
            (0, b"R  new.txt\0old.txt\0", ""),
            (1, b"", "error: hook rejected"),
        ]

        with patch(
            "mcp_workspace.git_operations.commits.run_git_raw",
            side_effect=responses,
        ):
            result = commit_paths("Hook", [Path("new.txt")], project_dir)

        assert result["error_category"] == "commit_failed"
        assert result["returncode"] == 1
