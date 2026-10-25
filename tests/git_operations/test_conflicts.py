"""Tests for conflict inspection and resolution."""

from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

import pytest
from git import Repo
from git.exc import GitCommandError

from mcp_workspace.git_operations import (
    get_conflict_blob_info,
    list_unmerged_paths,
    read_conflict_stage,
    rebase_start,
    resolve_take_theirs_or_remove,
)
from mcp_workspace.git_operations.core import run_git_raw
from tests.git_operations.conftest import FileChanges

BuildRepo = Callable[[FileChanges, FileChanges, FileChanges], tuple[Repo, Path]]

RUNNER = "mcp_workspace.git_operations.conflicts.run_git_raw"


def _stop_on_conflict(
    make_conflict_repo: BuildRepo,
    base: FileChanges,
    main_change: FileChanges,
    feature_change: FileChanges,
) -> Path:
    """Build diverged branches and rebase ``feature`` onto ``main`` to a stop."""
    _, project_dir = make_conflict_repo(base, main_change, feature_change)
    assert rebase_start(project_dir, "main")["status"] == "stopped_on_conflict"
    return project_dir


def _fail_cat_file(
    repo: Repo, command: str, *args: str, **kwargs: Any
) -> tuple[int, bytes, str]:
    """run_git_raw stand-in: ``cat_file`` fails, everything else runs for real."""
    if command == "cat_file":
        return 128, b"", "fatal: bad object"
    return run_git_raw(repo, command, *args, **kwargs)


class TestListUnmergedPaths:
    """list_unmerged_paths outcomes."""

    def test_no_conflict(self, make_conflict_repo: BuildRepo) -> None:
        """Nothing unmerged -> empty list."""
        _, project_dir = make_conflict_repo(
            {"a.txt": "base\n"}, {"a.txt": "main\n"}, {"a.txt": "feature\n"}
        )

        assert not list_unmerged_paths(project_dir)

    def test_two_conflicted_files(self, make_conflict_repo: BuildRepo) -> None:
        """Each conflicted path is listed once, in git's order."""
        _, project_dir = make_conflict_repo(
            {"a.txt": "base\n", "dätei.txt": "base\n"},
            {"a.txt": "main\n", "dätei.txt": "main\n"},
            {"a.txt": "feature\n", "dätei.txt": "feature\n"},
        )
        assert rebase_start(project_dir, "main")["status"] == "stopped_on_conflict"

        assert list_unmerged_paths(project_dir) == ["a.txt", "dätei.txt"]

    def test_non_repo_raises(self, tmp_path: Path) -> None:
        """A non-repository raises ValueError."""
        with pytest.raises(ValueError):
            list_unmerged_paths(tmp_path)

    def test_git_failure_raises(self, git_repo: tuple[Repo, Path]) -> None:
        """A nonzero exit raises GitCommandError."""
        _, project_dir = git_repo

        with patch(RUNNER, return_value=(128, b"", "fatal")):
            with pytest.raises(GitCommandError):
                list_unmerged_paths(project_dir)


class TestGetConflictBlobInfo:
    """get_conflict_blob_info outcomes."""

    def test_text_conflict(self, make_conflict_repo: BuildRepo) -> None:
        """A both-modified text file has all three stages and is not binary."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a.txt": "base\n"},
            {"a.txt": "main\n"},
            {"a.txt": "feature\n"},
        )

        result = get_conflict_blob_info(project_dir)

        assert result["success"]
        assert result["entries"] == [
            {"path": "a.txt", "stages": [1, 2, 3], "is_binary": False}
        ]

    def test_delete_modify_conflict(self, make_conflict_repo: BuildRepo) -> None:
        """Feature deletes, main modifies -> stage 3 is absent."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a.txt": "base\n"},
            {"a.txt": "main\n"},
            {"a.txt": None},
        )

        result = get_conflict_blob_info(project_dir)

        assert result["success"]
        assert result["entries"] == [
            {"path": "a.txt", "stages": [1, 2], "is_binary": False}
        ]

    def test_binary_conflict(self, make_conflict_repo: BuildRepo) -> None:
        """Content with a NUL byte marks the entry binary."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"blob.bin": b"base\0"},
            {"blob.bin": b"main\0"},
            {"blob.bin": b"feature\0"},
        )

        result = get_conflict_blob_info(project_dir)

        assert result["success"]
        assert result["entries"] == [
            {"path": "blob.bin", "stages": [1, 2, 3], "is_binary": True}
        ]

    def test_entries_sorted_by_path(self, make_conflict_repo: BuildRepo) -> None:
        """Entries come back sorted by path."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"z.txt": "base\n", "b/a.txt": "base\n", "m.txt": "base\n"},
            {"z.txt": "main\n", "b/a.txt": "main\n", "m.txt": "main\n"},
            {"z.txt": "feat\n", "b/a.txt": "feat\n", "m.txt": "feat\n"},
        )

        result = get_conflict_blob_info(project_dir)

        assert [entry["path"] for entry in result["entries"]] == [
            "b/a.txt",
            "m.txt",
            "z.txt",
        ]

    def test_no_conflict(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """Nothing unmerged -> success with no entries."""
        _, project_dir = git_repo_with_commit

        result = get_conflict_blob_info(project_dir)

        assert result["success"]
        assert not result["entries"]

    def test_cat_file_failure(self, make_conflict_repo: BuildRepo) -> None:
        """A failing blob read is a failed result."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a.txt": "base\n"},
            {"a.txt": "main\n"},
            {"a.txt": "feature\n"},
        )

        with patch(RUNNER, side_effect=_fail_cat_file):
            result = get_conflict_blob_info(project_dir)

        assert not result["success"]
        assert result["returncode"] == 128
        assert not result["entries"]

    def test_non_repo(self, tmp_path: Path) -> None:
        """A non-repository is a failed result, not an exception."""
        result = get_conflict_blob_info(tmp_path)

        assert not result["success"]
        assert result["error"]
        assert not result["entries"]


class TestReadConflictStage:
    """read_conflict_stage outcomes."""

    def test_ours_and_theirs(self, make_conflict_repo: BuildRepo) -> None:
        """Rebase: stage 2 is upstream (main), stage 3 the replayed commit."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a.txt": "base\n"},
            {"a.txt": "main\n"},
            {"a.txt": "feature\n"},
        )

        ours = read_conflict_stage(project_dir, 2, "a.txt")
        theirs = read_conflict_stage(project_dir, 3, "a.txt")
        base = read_conflict_stage(project_dir, 1, "a.txt")

        assert ours["success"] and ours["content"] == "main\n"
        assert theirs["success"] and theirs["content"] == "feature\n"
        assert base["success"] and base["content"] == "base\n"
        assert not ours["is_binary"]

    def test_long_content_byte_for_byte(self, make_conflict_repo: BuildRepo) -> None:
        """150 lines with a trailing newline come back unchanged."""
        main_text = "".join(f"main line {i}\n" for i in range(150))
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a.txt": "base\n"},
            {"a.txt": main_text},
            {"a.txt": "feature\n"},
        )

        result = read_conflict_stage(project_dir, 2, "a.txt")

        assert result["content"] == main_text

    def test_non_ascii_path_and_content(self, make_conflict_repo: BuildRepo) -> None:
        """Non-ASCII file names and content round-trip."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"dätei.txt": "base\n"},
            {"dätei.txt": "Grüße\n"},
            {"dätei.txt": "Ärger €\n"},
        )

        assert get_conflict_blob_info(project_dir)["entries"][0]["path"] == "dätei.txt"
        assert read_conflict_stage(project_dir, 2, "dätei.txt")["content"] == "Grüße\n"
        assert (
            read_conflict_stage(project_dir, 3, "dätei.txt")["content"] == "Ärger €\n"
        )

    def test_absent_stage(self, make_conflict_repo: BuildRepo) -> None:
        """A deleted side is success with no content."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a.txt": "base\n"},
            {"a.txt": "main\n"},
            {"a.txt": None},
        )

        result = read_conflict_stage(project_dir, 3, "a.txt")

        assert result["success"]
        assert result["content"] is None
        assert not result["is_binary"]

    def test_binary_stage(self, make_conflict_repo: BuildRepo) -> None:
        """A binary blob is reported, not decoded."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"blob.bin": b"base\0"},
            {"blob.bin": b"main\0"},
            {"blob.bin": b"feature\0"},
        )

        result = read_conflict_stage(project_dir, 2, "blob.bin")

        assert result["success"]
        assert result["content"] is None
        assert result["is_binary"]

    def test_invalid_stage(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A stage outside 1-3 fails without running git."""
        _, project_dir = git_repo_with_commit

        with patch(RUNNER) as runner:
            result = read_conflict_stage(project_dir, 4, "a.txt")

        assert not result["success"]
        assert result["returncode"] is None
        runner.assert_not_called()

    def test_cat_file_failure(self, make_conflict_repo: BuildRepo) -> None:
        """A failing blob read is a failed result."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a.txt": "base\n"},
            {"a.txt": "main\n"},
            {"a.txt": "feature\n"},
        )

        with patch(RUNNER, side_effect=_fail_cat_file):
            result = read_conflict_stage(project_dir, 2, "a.txt")

        assert not result["success"]
        assert result["returncode"] == 128
        assert result["content"] is None

    def test_non_repo(self, tmp_path: Path) -> None:
        """A non-repository is a failed result, not an exception."""
        result = read_conflict_stage(tmp_path, 2, "a.txt")

        assert not result["success"]
        assert result["error"]


class TestResolveTakeTheirsOrRemove:
    """resolve_take_theirs_or_remove outcomes."""

    def test_text_conflict_takes_feature(self, make_conflict_repo: BuildRepo) -> None:
        """Stage 3 (the replayed feature commit) is checked out and staged."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a.txt": "base\n"},
            {"a.txt": "main\n"},
            {"a.txt": "feature\n"},
        )
        repo = Repo(project_dir)

        result = resolve_take_theirs_or_remove(project_dir, "a.txt")

        assert result["success"]
        assert result["error"] is None
        assert (project_dir / "a.txt").read_bytes() == b"feature\n"
        assert not list_unmerged_paths(project_dir)
        assert repo.git.diff("--cached", "--name-only") == "a.txt"
        assert repo.git.show(":a.txt") == "feature"

    def test_delete_modify_removes(self, make_conflict_repo: BuildRepo) -> None:
        """Feature deleted the file -> removed from index and disk."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a.txt": "base\n"},
            {"a.txt": "main\n"},
            {"a.txt": None},
        )
        repo = Repo(project_dir)

        result = resolve_take_theirs_or_remove(project_dir, "a.txt")

        assert result["success"]
        assert not (project_dir / "a.txt").exists()
        assert not repo.git.ls_files("--", "a.txt")
        assert not list_unmerged_paths(project_dir)

    def test_bracket_path_is_literal(self, make_conflict_repo: BuildRepo) -> None:
        """``a[b].txt`` resolves only itself, not the glob match ``ab.txt``."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a[b].txt": "base\n", "ab.txt": "base\n"},
            {"a[b].txt": "main\n", "ab.txt": "main\n"},
            {"a[b].txt": "feature\n", "ab.txt": "feature\n"},
        )

        result = resolve_take_theirs_or_remove(project_dir, "a[b].txt")

        assert result["success"]
        assert (project_dir / "a[b].txt").read_bytes() == b"feature\n"
        assert list_unmerged_paths(project_dir) == ["ab.txt"]

    def test_magic_pathspec_is_literal(self, make_conflict_repo: BuildRepo) -> None:
        """A magic pathspec matches no unmerged path and resolves nothing."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a.txt": "base\n"},
            {"a.txt": "main\n"},
            {"a.txt": "feature\n"},
        )

        result = resolve_take_theirs_or_remove(project_dir, ":(glob)*.txt")

        assert not result["success"]
        assert result["error"] is not None
        assert "not unmerged" in result["error"]
        assert list_unmerged_paths(project_dir) == ["a.txt"]

    def test_non_conflicted_path(self, make_conflict_repo: BuildRepo) -> None:
        """A path with no unmerged entries is a failed result."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a.txt": "base\n", "b.txt": "same\n"},
            {"a.txt": "main\n"},
            {"a.txt": "feature\n"},
        )

        result = resolve_take_theirs_or_remove(project_dir, "b.txt")

        assert not result["success"]
        assert result["error"] is not None
        assert "not unmerged" in result["error"]
        assert list_unmerged_paths(project_dir) == ["a.txt"]

    def test_git_failure(self, make_conflict_repo: BuildRepo) -> None:
        """A failing git call is a failed result carrying its exit code."""
        project_dir = _stop_on_conflict(
            make_conflict_repo,
            {"a.txt": "base\n"},
            {"a.txt": "main\n"},
            {"a.txt": "feature\n"},
        )

        def fail_checkout(
            repo: Repo, command: str, *args: str, **kwargs: Any
        ) -> tuple[int, bytes, str]:
            if command == "checkout":
                return 1, b"", "error: checkout failed"
            return run_git_raw(repo, command, *args, **kwargs)

        with patch(RUNNER, side_effect=fail_checkout):
            result = resolve_take_theirs_or_remove(project_dir, "a.txt")

        assert not result["success"]
        assert result["returncode"] == 1
        assert result["stderr"] == "error: checkout failed"
        assert list_unmerged_paths(project_dir) == ["a.txt"]

    def test_non_repo(self, tmp_path: Path) -> None:
        """A non-repository is a failed result, not an exception."""
        result = resolve_take_theirs_or_remove(tmp_path, "a.txt")

        assert not result["success"]
        assert result["error"]
