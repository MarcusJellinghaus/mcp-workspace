"""Tests for list_tree."""

from pathlib import Path

from git import Repo

from mcp_workspace.git_operations import list_tree
from tests.git_operations.conftest import commit_files


def _pr_info_repo(git_repo: tuple[Repo, Path]) -> tuple[Repo, Path]:
    """Commit ``pr_info/a.md`` and ``pr_info/sub/b.md`` on ``main``."""
    repo, project_dir = git_repo
    commit_files(
        repo,
        {"pr_info/a.md": "a\n", "pr_info/sub/b.md": "b\n", "README.md": "r\n"},
        "add pr_info",
    )
    repo.git.branch("-M", "main")
    return repo, project_dir


class TestListTree:
    """Tests for list_tree."""

    def test_lists_directory_contents_without_recursion(
        self, git_repo: tuple[Repo, Path]
    ) -> None:
        """Only the direct children of ``path`` are listed."""
        _, project_dir = _pr_info_repo(git_repo)

        result = list_tree(project_dir, "HEAD", "pr_info")

        assert result["success"] is True
        assert result["error"] is None
        assert [(e["type"], e["path"]) for e in result["entries"]] == [
            ("blob", "pr_info/a.md"),
            ("tree", "pr_info/sub"),
        ]
        assert result["entries"][0]["mode"] == "100644"
        assert len(result["entries"][0]["sha"]) == 40

    def test_trailing_slash_is_accepted(self, git_repo: tuple[Repo, Path]) -> None:
        """``pr_info/`` and ``pr_info`` list the same entries."""
        _, project_dir = _pr_info_repo(git_repo)

        assert (
            list_tree(project_dir, "HEAD", "pr_info/")["entries"]
            == list_tree(project_dir, "HEAD", "pr_info")["entries"]
        )

    def test_reads_other_ref_than_checked_out(
        self, git_repo: tuple[Repo, Path]
    ) -> None:
        """A ref other than the checked-out branch is read from its tree."""
        repo, project_dir = _pr_info_repo(git_repo)
        repo.git.checkout("-b", "feature")
        commit_files(
            repo, {"pr_info/a.md": None, "pr_info/c.md": "c\n"}, "feature change"
        )

        result = list_tree(project_dir, "main", "pr_info")

        assert result["success"] is True
        assert [e["path"] for e in result["entries"]] == [
            "pr_info/a.md",
            "pr_info/sub",
        ]

    def test_literal_path(self, git_repo: tuple[Repo, Path]) -> None:
        """Glob characters in ``path`` are matched literally."""
        repo, project_dir = git_repo
        commit_files(repo, {"d[x]/a.md": "a\n", "dx/b.md": "b\n"}, "add")

        result = list_tree(project_dir, "HEAD", "d[x]")

        assert [e["path"] for e in result["entries"]] == ["d[x]/a.md"]

    def test_non_ascii_path(self, git_repo: tuple[Repo, Path]) -> None:
        """Non-ASCII paths round-trip."""
        repo, project_dir = git_repo
        commit_files(repo, {"dir/dätei_日本.md": "x\n"}, "add")

        result = list_tree(project_dir, "HEAD", "dir")

        assert [e["path"] for e in result["entries"]] == ["dir/dätei_日本.md"]

    def test_missing_directory_is_empty_success(
        self, git_repo: tuple[Repo, Path]
    ) -> None:
        """A path absent at ``ref`` is a successful empty listing."""
        _, project_dir = _pr_info_repo(git_repo)

        result = list_tree(project_dir, "HEAD", "nope")

        assert result["success"] is True
        assert not result["entries"]

    def test_bad_ref_fails(self, git_repo: tuple[Repo, Path]) -> None:
        """An unknown ref is a failed result."""
        _, project_dir = _pr_info_repo(git_repo)

        result = list_tree(project_dir, "no-such-ref", "pr_info")

        assert result["success"] is False
        assert result["error"]
        assert result["returncode"] not in (None, 0)
        assert not result["entries"]

    def test_option_like_ref_rejected(self, git_repo: tuple[Repo, Path]) -> None:
        """A ref starting with ``-`` is rejected without running git."""
        _, project_dir = _pr_info_repo(git_repo)

        result = list_tree(project_dir, "-x", "pr_info")

        assert result["success"] is False
        assert result["returncode"] is None
        assert not result["entries"]

    def test_empty_ref_rejected(self, git_repo: tuple[Repo, Path]) -> None:
        """An empty ref is rejected without running git."""
        _, project_dir = _pr_info_repo(git_repo)

        result = list_tree(project_dir, "", "pr_info")

        assert result["success"] is False
        assert result["returncode"] is None

    def test_non_repo(self, tmp_path: Path) -> None:
        """A non-repository is a failed result, not an exception."""
        result = list_tree(tmp_path, "HEAD", "pr_info")

        assert result["success"] is False
        assert result["error"]
        assert not result["entries"]
