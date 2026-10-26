"""Tests for probe_rebase_conflicts."""

from pathlib import Path
from typing import Callable
from unittest.mock import patch

import pytest
from git import Repo

from mcp_workspace.git_operations import probe_rebase_conflicts
from tests.git_operations.conftest import FileChanges

BuildRepo = Callable[[FileChanges, FileChanges, FileChanges], tuple[Repo, Path]]

RUNNER = "mcp_workspace.git_operations.rebase.run_git_raw"
VERSION = "mcp_workspace.git_operations.rebase._git_version"


class TestProbeRebaseConflictsRealRepo:
    """probe_rebase_conflicts against real repositories."""

    def test_conflict(self, make_conflict_repo: BuildRepo) -> None:
        """Both sides change the same line -> conflict, error None."""
        _, project_dir = make_conflict_repo(
            {"dätei.txt": "base\n", "other.txt": "x\n"},
            {"dätei.txt": "main\n"},
            {"dätei.txt": "feature\n"},
        )

        result = probe_rebase_conflicts(project_dir, "main")

        assert result["status"] == "conflict"
        assert result["success"] is False
        assert result["error"] is None
        assert result["files"] == ["dätei.txt"]
        assert result["returncode"] == 1

    def test_clean(self, make_conflict_repo: BuildRepo) -> None:
        """Non-overlapping changes -> clean."""
        _, project_dir = make_conflict_repo(
            {"a.txt": "a\n", "b.txt": "b\n"},
            {"a.txt": "a main\n"},
            {"b.txt": "b feature\n"},
        )

        result = probe_rebase_conflicts(project_dir, "main")

        assert result["status"] == "clean"
        assert result["success"] is True
        assert result["error"] is None
        assert not result["files"]

    def test_bad_ref_is_error(self, make_conflict_repo: BuildRepo) -> None:
        """An unknown ref is an error, not a conflict."""
        _, project_dir = make_conflict_repo(
            {"a.txt": "a\n"}, {"a.txt": "main\n"}, {"a.txt": "feature\n"}
        )

        result = probe_rebase_conflicts(project_dir, "no-such-ref")

        assert result["status"] == "error"
        assert result["success"] is False
        assert result["error"]
        assert not result["files"]

    def test_option_like_ref_is_error(self, git_repo: tuple[Repo, Path]) -> None:
        """A ref starting with '-' is rejected without running git."""
        _, project_dir = git_repo

        with patch(RUNNER) as runner:
            result = probe_rebase_conflicts(project_dir, "-x")

        runner.assert_not_called()
        assert result["status"] == "error"
        assert result["success"] is False
        assert result["returncode"] is None

    def test_non_repo_is_error(self, tmp_path: Path) -> None:
        """A directory that is not a repository is an error result."""
        result = probe_rebase_conflicts(tmp_path, "main")

        assert result["status"] == "error"
        assert result["success"] is False
        assert result["returncode"] is None
        assert result["stderr"] is None


class TestProbeRebaseConflictsMocked:
    """Exit-code branches driven through a mocked runner."""

    def test_exit_1_with_empty_stdout_is_error(
        self, git_repo: tuple[Repo, Path]
    ) -> None:
        """Exit 1 without a tree oid is an error, not a conflict."""
        _, project_dir = git_repo

        with patch(RUNNER, return_value=(1, b"", "fatal: bad revision")):
            result = probe_rebase_conflicts(project_dir, "main")

        assert result["status"] == "error"
        assert result["success"] is False
        assert result["returncode"] == 1
        assert result["stderr"] == "fatal: bad revision"

    @pytest.mark.parametrize(
        ("version", "expected"),
        [((2, 37), "unsupported"), ((2, 40), "error")],
    )
    def test_usage_error_depends_on_version(
        self,
        git_repo: tuple[Repo, Path],
        version: tuple[int, int],
        expected: str,
    ) -> None:
        """Any other exit code is unsupported below git 2.38, else error."""
        _, project_dir = git_repo

        with (
            patch(RUNNER, return_value=(129, b"", "usage")),
            patch(VERSION, return_value=version),
        ):
            result = probe_rebase_conflicts(project_dir, "main")

        assert result["status"] == expected
        assert result["success"] is False
        assert result["returncode"] == 129
        assert result["error"]
