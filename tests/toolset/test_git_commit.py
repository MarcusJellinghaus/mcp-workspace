"""Tests for the git_commit tool."""

import asyncio
import os
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from git import Repo

from mcp_workspace.toolset import tool_specs
from mcp_workspace.toolset._git_write_helpers import format_commit_result

_HELPERS = "mcp_workspace.toolset._git_write_helpers"
_OK = {"success": True, "error": None, "returncode": 0, "stderr": ""}


def _git_commit(
    project_dir: Path,
    message: str = "Commit",
    paths: list[str] | None = None,
    all: bool = False,  # pylint: disable=redefined-builtin
) -> str:
    """Call the git_commit tool of a fresh tool set."""
    spec = {s.name: s for s in tool_specs(project_dir)}["git_commit"]
    result: str = asyncio.run(spec.fn(message=message, paths=paths, all=all))
    return result


def _commit_result(
    success: bool,
    commit_hash: str | None = None,
    error: str | None = None,
    error_category: str | None = None,
) -> dict[str, Any]:
    """Build a CommitResult."""
    return {
        "success": success,
        "commit_hash": commit_hash,
        "error": error,
        "error_category": error_category,
        "returncode": 0 if success else 1,
        "stderr": None,
    }


@pytest.fixture
def lib() -> Iterator[dict[str, MagicMock]]:
    """Patch the library functions where the helper module imports them.

    By default ``main`` is checked out, nothing is in progress, ``new.txt`` is
    the only untracked file and every commit succeeds as ``abc1234``.
    """
    defaults: dict[str, Any] = {
        "operation_in_progress": None,
        "get_current_branch_name": "main",
        "list_untracked_paths": ["new.txt"],
        "stage_paths": _OK,
        "unstage_paths": _OK,
        "commit_paths": _commit_result(True, "abc1234"),
        "commit_all_changes": _commit_result(True, "abc1234"),
        "committed_files": ["a.txt", "new.txt"],
        "format_dirty_tree": "",
    }
    patchers = {
        name: patch(f"{_HELPERS}.{name}", return_value=value)
        for name, value in defaults.items()
    }
    mocks = {name: p.start() for name, p in patchers.items()}
    yield mocks
    for p in patchers.values():
        p.stop()


class TestGitCommitUnit:
    """git_commit guardrails and orchestration with the library patched."""

    @pytest.mark.parametrize(
        ("paths", "all_"),
        [(None, False), ([], False), (["a.txt"], True)],
        ids=["neither", "empty-paths", "both"],
    )
    def test_exactly_one_of_paths_or_all(
        self,
        tmp_path: Path,
        lib: dict[str, MagicMock],
        paths: list[str] | None,
        all_: bool,
    ) -> None:
        """Neither or both of paths / all is refused; [] counts as not given."""
        result = _git_commit(tmp_path, paths=paths, all=all_)

        assert result == "Error: pass exactly one of paths or all=True"
        for mock in lib.values():
            mock.assert_not_called()

    def test_empty_paths_with_all(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """paths=[] is "not given", so it combines with all=True."""
        result = _git_commit(tmp_path, paths=[], all=True)

        assert result.startswith("Committed abc1234")
        lib["commit_all_changes"].assert_called_once()

    def test_empty_message(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A blank message is refused before anything is staged."""
        result = _git_commit(tmp_path, message="  ", all=True)

        assert result == "Error: commit message is empty"
        lib["commit_all_changes"].assert_not_called()

    def test_detached_head(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A detached HEAD is refused."""
        lib["get_current_branch_name"].return_value = None

        result = _git_commit(tmp_path, paths=["a.txt"])

        assert result.startswith("Error: HEAD is detached")
        lib["stage_paths"].assert_not_called()
        lib["commit_paths"].assert_not_called()

    @pytest.mark.parametrize("op", ["rebase", "merge"])
    def test_operation_in_progress(
        self, tmp_path: Path, lib: dict[str, MagicMock], op: str
    ) -> None:
        """A stopped rebase or merge is refused."""
        lib["operation_in_progress"].return_value = op

        result = _git_commit(tmp_path, all=True)

        assert result == f"Error: a {op} is in progress; finish or abort it first"
        lib["commit_all_changes"].assert_not_called()

    def test_commit_paths_success(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """Untracked files under paths are staged, then exactly paths committed."""
        lib["format_dirty_tree"].return_value = "\nWorking tree:\n  modified: b.txt"

        result = _git_commit(tmp_path, message="Msg", paths=["a.txt", "new.txt"])

        assert result == (
            "Committed abc1234 on main (2 files)\n"
            "  a.txt\n"
            "  new.txt\n"
            "Working tree:\n"
            "  modified: b.txt"
        )
        given = [Path("a.txt"), Path("new.txt")]
        lib["list_untracked_paths"].assert_called_once_with(given, tmp_path)
        lib["stage_paths"].assert_called_once_with([Path("new.txt")], tmp_path)
        lib["commit_paths"].assert_called_once_with("Msg", given, tmp_path)
        lib["unstage_paths"].assert_not_called()

    def test_commit_failure_unstages_new_files(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """A failed commit unstages exactly the untracked files it staged."""
        lib["list_untracked_paths"].return_value = ["new.txt", "dir/other.txt"]
        lib["commit_paths"].return_value = _commit_result(
            False, error="Git error creating commit: hook failed"
        )

        result = _git_commit(tmp_path, paths=["a.txt", "new.txt", "dir"])

        assert result == "Error: Git error creating commit: hook failed"
        lib["unstage_paths"].assert_called_once_with(
            [Path("new.txt"), Path("dir/other.txt")], tmp_path
        )

    def test_staging_failure(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A failed git add unstages the untracked files and commits nothing."""
        lib["stage_paths"].return_value = {
            "success": False,
            "error": "git add failed (exit 128)",
            "returncode": 128,
            "stderr": "fatal: oops\n",
        }

        result = _git_commit(tmp_path, paths=["new.txt"])

        assert result.startswith("Error: git add failed (exit 128)")
        lib["unstage_paths"].assert_called_once_with([Path("new.txt")], tmp_path)
        lib["commit_paths"].assert_not_called()

    def test_all_clean_tree(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """commit_all_changes succeeding without a commit is Nothing to commit."""
        lib["commit_all_changes"].return_value = _commit_result(True)

        result = _git_commit(tmp_path, all=True)

        assert result == "Nothing to commit"
        lib["committed_files"].assert_not_called()

    def test_all_no_staged_files(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """'No staged files to commit' is Nothing to commit, not an error."""
        lib["commit_all_changes"].return_value = _commit_result(
            False, error="No staged files to commit", error_category="validation_failed"
        )
        lib["format_dirty_tree"].return_value = "\nWorking tree:\n  untracked: x"

        result = _git_commit(tmp_path, all=True)

        assert result == "Nothing to commit\nWorking tree:\n  untracked: x"

    def test_paths_nothing_to_commit_names_paths(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """Nothing to commit for paths names them, so a typo is visible."""
        lib["list_untracked_paths"].return_value = []
        lib["commit_paths"].return_value = _commit_result(
            False,
            error="Nothing to commit for the given paths",
            error_category="nothing_to_commit",
        )

        result = _git_commit(tmp_path, paths=["src/mian.py", "b.txt"])

        assert result.splitlines()[0] == (
            "Nothing to commit for paths: src/mian.py, b.txt"
        )
        lib["unstage_paths"].assert_not_called()

    def test_all_success(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """all=True commits through commit_all_changes."""
        result = _git_commit(tmp_path, message="Msg", all=True)

        assert result == "Committed abc1234 on main (2 files)\n  a.txt\n  new.txt"
        lib["commit_all_changes"].assert_called_once_with("Msg", tmp_path)
        lib["commit_paths"].assert_not_called()
        lib["stage_paths"].assert_not_called()

    def test_file_list_capped(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A long committed file list is truncated with a count."""
        lib["committed_files"].return_value = [f"f{i:03}.txt" for i in range(60)]

        lines = _git_commit(tmp_path, all=True).splitlines()

        assert lines[0] == "Committed abc1234 on main (60 files)"
        assert lines[1] == "  f000.txt"
        assert lines[50] == "  f049.txt"
        assert lines[51] == "  ... showing 50 of 60 files"
        assert len(lines) == 52

    def test_library_raises(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """An exception becomes an error result."""
        lib["commit_all_changes"].side_effect = RuntimeError("boom")

        assert _git_commit(tmp_path, all=True) == "Error: boom"


def test_format_commit_result_singular() -> None:
    """One file is reported as '1 file'."""
    assert format_commit_result("abc1234", "x", ["a"]) == (
        "Committed abc1234 on x (1 file)\n  a"
    )


def _seed(project_dir: Path, *names: str) -> None:
    """Commit one file per name."""
    repo = Repo(project_dir)
    for name in names:
        (project_dir / name).write_text(f"{name}\n")
    repo.index.add(list(names))
    repo.index.commit("Seed")


def _head_files(project_dir: Path) -> list[str]:
    """Return the paths changed by HEAD."""
    out = Repo(project_dir).git.diff_tree("--no-commit-id", "--name-only", "-r", "HEAD")
    return str(out).splitlines()


def _untracked(project_dir: Path) -> list[str]:
    """Return the untracked files."""
    return list(Repo(project_dir).untracked_files)


def _staged(project_dir: Path) -> list[str]:
    """Return the paths staged relative to HEAD."""
    return str(Repo(project_dir).git.diff("--cached", "--name-only")).splitlines()


@pytest.mark.git_integration
class TestGitCommitIntegration:
    """git_commit against a real clone."""

    def test_paths_modified_deleted_new(self, origin_clone: Path) -> None:
        """Modified, deleted and new files are committed; the rest stays."""
        _seed(origin_clone, "a.txt", "b.txt", "c.txt")
        (origin_clone / "a.txt").write_text("changed\n")
        (origin_clone / "b.txt").unlink()
        (origin_clone / "new.txt").write_text("new\n")
        (origin_clone / "c.txt").write_text("not committed\n")

        result = _git_commit(origin_clone, paths=["a.txt", "b.txt", "new.txt"])

        sha = Repo(origin_clone).head.commit.hexsha[:7]
        head, _, tree = result.partition("\nWorking tree:\n")
        assert head == (
            f"Committed {sha} on main (3 files)\n  a.txt\n  b.txt\n  new.txt"
        )
        assert "c.txt" in tree
        assert _head_files(origin_clone) == ["a.txt", "b.txt", "new.txt"]
        assert "c.txt" in Repo(origin_clone).git.diff("--name-only")

    def test_paths_directory_with_nested_new_files(self, origin_clone: Path) -> None:
        """A directory path includes the new files beneath it."""
        (origin_clone / "newdir" / "sub").mkdir(parents=True)
        (origin_clone / "newdir" / "a.txt").write_text("a\n")
        (origin_clone / "newdir" / "sub" / "b.txt").write_text("b\n")

        result = _git_commit(origin_clone, paths=["newdir"])

        assert result.startswith("Committed ")
        assert "(2 files)" in result
        assert _head_files(origin_clone) == ["newdir/a.txt", "newdir/sub/b.txt"]
        assert not _untracked(origin_clone)

    def test_prestaged_file_outside_paths_stays_staged(
        self, origin_clone: Path
    ) -> None:
        """A file staged beforehand but not in paths is left staged."""
        _seed(origin_clone, "a.txt", "staged.txt")
        (origin_clone / "a.txt").write_text("changed\n")
        (origin_clone / "staged.txt").write_text("staged\n")
        Repo(origin_clone).index.add(["staged.txt"])

        result = _git_commit(origin_clone, paths=["a.txt"])

        assert result.startswith("Committed ")
        assert _head_files(origin_clone) == ["a.txt"]
        assert _staged(origin_clone) == ["staged.txt"]

    def test_all_commits_everything_then_nothing(self, origin_clone: Path) -> None:
        """all=True commits untracked files too; a clean tree has nothing."""
        _seed(origin_clone, "a.txt")
        (origin_clone / "a.txt").write_text("changed\n")
        (origin_clone / "new.txt").write_text("new\n")

        result = _git_commit(origin_clone, all=True)

        assert result.startswith("Committed ")
        assert "Working tree:" not in result
        assert _head_files(origin_clone) == ["a.txt", "new.txt"]

        assert _git_commit(origin_clone, all=True) == "Nothing to commit"

    def test_mistyped_path(self, origin_clone: Path) -> None:
        """A path that does not exist is named in Nothing to commit."""
        result = _git_commit(origin_clone, paths=["READMEE.md"])

        assert result == "Nothing to commit for paths: READMEE.md"

    def test_failing_pre_commit_hook(self, origin_clone: Path, tmp_path: Path) -> None:
        """A failing hook fails the commit; the new files are untracked again."""
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        hook = hooks / "pre-commit"
        hook.write_text("#!/bin/sh\necho 'hook says no' >&2\nexit 1\n", newline="\n")
        if os.name != "nt":
            hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
        with Repo(origin_clone).config_writer() as cfg:
            cfg.set_value("core", "hooksPath", hooks.as_posix())
        head = Repo(origin_clone).head.commit.hexsha
        (origin_clone / "new.txt").write_text("new\n")
        (origin_clone / "README.md").write_text("changed\n")

        result = _git_commit(origin_clone, paths=["new.txt", "README.md"])

        assert result.startswith("Error: ")
        assert "hook says no" in result
        assert Repo(origin_clone).head.commit.hexsha == head
        assert _untracked(origin_clone) == ["new.txt"]
        assert not _staged(origin_clone)
