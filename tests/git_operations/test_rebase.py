"""Tests for the rebase flow (is_rebase_in_progress, rebase_*) and reset_hard."""

from pathlib import Path
from typing import Callable
from unittest.mock import patch

import pytest
from git import Repo

from mcp_workspace.git_operations import (
    is_rebase_in_progress,
    rebase_abort,
    rebase_continue,
    rebase_skip,
    rebase_start,
    reset_hard,
    stage_all_changes,
)
from mcp_workspace.git_operations.core import run_git_raw
from tests.git_operations.conftest import FileChanges, commit_files

BuildRepo = Callable[[FileChanges, FileChanges, FileChanges], tuple[Repo, Path]]

RUNNER = "mcp_workspace.git_operations.rebase.run_git_raw"


def _conflicting(make_conflict_repo: BuildRepo) -> tuple[Repo, Path]:
    """Build main and feature that conflict on one line of dätei.txt."""
    return make_conflict_repo(
        {"dätei.txt": "base\n"}, {"dätei.txt": "main\n"}, {"dätei.txt": "feature\n"}
    )


def _write(path: Path, text: str) -> None:
    """Write ``text`` as UTF-8 with LF endings (``write_text`` uses CRLF on Windows)."""
    path.write_bytes(text.encode("utf-8"))


def _unmerged(repo: Repo) -> bytes:
    """Return raw ``ls-files -u`` output (empty when nothing is unmerged)."""
    _, out, _ = run_git_raw(repo, "ls_files", "-u", "-z")
    return out


class TestRebaseStart:
    """rebase_start outcomes."""

    def test_already_up_to_date(self, make_conflict_repo: BuildRepo) -> None:
        """Rebasing onto an ancestor completes."""
        _, project_dir = _conflicting(make_conflict_repo)

        result = rebase_start(project_dir, "feature~1")

        assert result["status"] == "completed"
        assert result["success"] is True
        assert result["error"] is None
        assert result["returncode"] == 0

    def test_clean_rebase(self, make_conflict_repo: BuildRepo) -> None:
        """Non-overlapping changes rebase cleanly."""
        repo, project_dir = make_conflict_repo(
            {"a.txt": "a\n", "b.txt": "b\n"},
            {"a.txt": "a main\n"},
            {"b.txt": "b feature\n"},
        )
        main_sha = repo.git.rev_parse("main")

        result = rebase_start(project_dir, "main")

        assert result["status"] == "completed"
        assert result["success"] is True
        assert repo.git.rev_parse("HEAD~1") == main_sha
        assert not is_rebase_in_progress(project_dir)

    def test_text_conflict_stops(self, make_conflict_repo: BuildRepo) -> None:
        """A text conflict stops the rebase with error None."""
        repo, project_dir = _conflicting(make_conflict_repo)

        result = rebase_start(project_dir, "main")

        assert result["status"] == "stopped_on_conflict"
        assert result["success"] is False
        assert result["error"] is None
        assert result["returncode"] not in (None, 0)
        assert is_rebase_in_progress(project_dir)
        assert _unmerged(repo)

    def test_dirty_tree_refuses(self, make_conflict_repo: BuildRepo) -> None:
        """Unstaged changes make git refuse to start -> error, not in progress."""
        _, project_dir = _conflicting(make_conflict_repo)
        _write(project_dir / "dätei.txt", "dirty\n")

        result = rebase_start(project_dir, "main")

        assert result["status"] == "error"
        assert result["success"] is False
        assert result["error"]
        assert result["returncode"] not in (None, 0)
        assert not is_rebase_in_progress(project_dir)

    def test_already_in_progress(self, make_conflict_repo: BuildRepo) -> None:
        """Starting while a rebase is stopped is an error without running git."""
        _, project_dir = _conflicting(make_conflict_repo)
        assert rebase_start(project_dir, "main")["status"] == "stopped_on_conflict"

        with patch(RUNNER) as runner:
            result = rebase_start(project_dir, "main")

        runner.assert_not_called()
        assert result["status"] == "error"
        assert result["error"] == "A rebase is already in progress"
        assert result["returncode"] is None
        assert is_rebase_in_progress(project_dir)

    def test_option_like_ref(self, git_repo: tuple[Repo, Path]) -> None:
        """A ref starting with '-' is rejected without running git."""
        _, project_dir = git_repo

        with patch(RUNNER) as runner:
            result = rebase_start(project_dir, "-x")

        runner.assert_not_called()
        assert result["status"] == "error"
        assert result["success"] is False
        assert result["returncode"] is None

    def test_non_repo(self, tmp_path: Path) -> None:
        """A non-repository is an error result."""
        result = rebase_start(tmp_path, "main")

        assert result["status"] == "error"
        assert result["success"] is False
        assert result["returncode"] is None
        assert result["stderr"] is None


class TestRebaseContinueAndSkip:
    """Driving a stopped rebase to completion."""

    def test_multi_commit_conflicts(self, make_conflict_repo: BuildRepo) -> None:
        """Two conflicting commits: stop, continue stops again, continue completes."""
        repo, project_dir = make_conflict_repo(
            {"a.txt": "base\n", "b.txt": "base\n"},
            {"a.txt": "main\n", "b.txt": "main\n"},
            {"a.txt": "feature\n"},
        )
        commit_files(repo, {"b.txt": "feature\n"}, "feature change 2")

        first = rebase_start(project_dir, "main")
        assert first["status"] == "stopped_on_conflict"

        _write(project_dir / "a.txt", "resolved a\n")
        assert stage_all_changes(project_dir)
        second = rebase_continue(project_dir)
        assert second["status"] == "stopped_on_conflict"
        assert second["error"] is None
        assert is_rebase_in_progress(project_dir)

        _write(project_dir / "b.txt", "resolved b\n")
        assert stage_all_changes(project_dir)
        third = rebase_continue(project_dir)

        assert third["status"] == "completed"
        assert third["success"] is True
        assert not is_rebase_in_progress(project_dir)
        assert repo.git.rev_parse("HEAD~2") == repo.git.rev_parse("main")
        assert (project_dir / "a.txt").read_bytes() == b"resolved a\n"
        assert (project_dir / "b.txt").read_bytes() == b"resolved b\n"

    def test_empty_commit_stop_then_skip(self, make_conflict_repo: BuildRepo) -> None:
        """Resolving to the main side stops with nothing unmerged; skip completes.

        The default merge backend drops the now-empty commit on --continue,
        so the apply backend is used to force the stop.
        """
        repo, project_dir = _conflicting(make_conflict_repo)
        repo.git.config("rebase.backend", "apply")
        assert rebase_start(project_dir, "main")["status"] == "stopped_on_conflict"

        _write(project_dir / "dätei.txt", "main\n")
        assert stage_all_changes(project_dir)
        stopped = rebase_continue(project_dir)

        assert stopped["status"] == "stopped_on_conflict"
        assert stopped["error"] is None
        assert is_rebase_in_progress(project_dir)
        assert _unmerged(repo) == b""

        skipped = rebase_skip(project_dir)

        assert skipped["status"] == "completed"
        assert skipped["success"] is True
        assert not is_rebase_in_progress(project_dir)
        assert repo.git.rev_parse("HEAD") == repo.git.rev_parse("main")

    def test_continue_without_rebase(self, make_conflict_repo: BuildRepo) -> None:
        """--continue with nothing in progress is an error."""
        _, project_dir = _conflicting(make_conflict_repo)

        result = rebase_continue(project_dir)

        assert result["status"] == "error"
        assert result["success"] is False
        assert result["error"]
        assert result["returncode"] not in (None, 0)


class TestRebaseAbort:
    """rebase_abort outcomes."""

    def test_abort_during_conflict(self, make_conflict_repo: BuildRepo) -> None:
        """Abort restores the feature tip."""
        repo, project_dir = _conflicting(make_conflict_repo)
        feature_tip = repo.git.rev_parse("HEAD")
        assert rebase_start(project_dir, "main")["status"] == "stopped_on_conflict"

        result = rebase_abort(project_dir)

        assert result["success"] is True
        assert result["error"] is None
        assert result["returncode"] == 0
        assert not is_rebase_in_progress(project_dir)
        assert repo.git.rev_parse("HEAD") == feature_tip

    def test_abort_nothing_in_progress(self, make_conflict_repo: BuildRepo) -> None:
        """Abort with no rebase is a no-op success without running git."""
        _, project_dir = _conflicting(make_conflict_repo)

        with patch(RUNNER) as runner:
            result = rebase_abort(project_dir)

        runner.assert_not_called()
        assert result["success"] is True
        assert result["returncode"] is None

    def test_abort_non_repo(self, tmp_path: Path) -> None:
        """A non-repository is an error result."""
        result = rebase_abort(tmp_path)

        assert result["success"] is False
        assert result["error"]


class TestIsRebaseInProgress:
    """is_rebase_in_progress outside the simple single-checkout case."""

    def test_worktree(self, make_conflict_repo: BuildRepo) -> None:
        """A rebase stopped in a worktree is reported there, not in main checkout."""
        repo, project_dir = _conflicting(make_conflict_repo)
        # ASCII on purpose: GitPython reads the worktree's .git file with the
        # locale code page, so it cannot open a non-ASCII worktree path on Windows
        worktree = project_dir.parent / "worktree"
        repo.git.worktree("add", "-b", "feature2", str(worktree), "feature")

        result = rebase_start(worktree, "main")

        assert result["status"] == "stopped_on_conflict"
        assert is_rebase_in_progress(worktree) is True
        assert is_rebase_in_progress(project_dir) is False

    def test_non_repo_raises(self, tmp_path: Path) -> None:
        """A non-repository raises ValueError."""
        with pytest.raises(ValueError):
            is_rebase_in_progress(tmp_path)


class TestResetHard:
    """reset_hard outcomes."""

    def test_resets_to_earlier_commit(self, git_repo: tuple[Repo, Path]) -> None:
        """HEAD and working tree move back to the given sha."""
        repo, project_dir = git_repo
        first_sha = commit_files(repo, {"dätei.txt": "first\n"}, "first")
        commit_files(repo, {"dätei.txt": "second\n", "neu.txt": "new\n"}, "second")

        result = reset_hard(project_dir, first_sha)

        assert result["success"] is True
        assert result["error"] is None
        assert result["returncode"] == 0
        assert repo.git.rev_parse("HEAD") == first_sha
        # read_text: checkout may convert to CRLF (core.autocrlf)
        assert (project_dir / "dätei.txt").read_text(encoding="utf-8") == "first\n"
        assert not (project_dir / "neu.txt").exists()

    def test_discards_uncommitted_change(self, git_repo: tuple[Repo, Path]) -> None:
        """Uncommitted changes to tracked files are discarded."""
        repo, project_dir = git_repo
        sha = commit_files(repo, {"a.txt": "committed\n"}, "commit")
        _write(project_dir / "a.txt", "dirty\n")

        result = reset_hard(project_dir, sha)

        assert result["success"] is True
        assert (project_dir / "a.txt").read_text(encoding="utf-8") == "committed\n"
        assert repo.git.status("--porcelain") == ""

    def test_unknown_sha(self, git_repo: tuple[Repo, Path]) -> None:
        """An unknown sha is an error result carrying git's exit code."""
        repo, project_dir = git_repo
        commit_files(repo, {"a.txt": "a\n"}, "commit")

        result = reset_hard(project_dir, "0" * 40)

        assert result["success"] is False
        assert result["error"]
        assert result["returncode"] not in (None, 0)

    @pytest.mark.parametrize("sha", ["-x", ""])
    def test_invalid_sha(self, git_repo: tuple[Repo, Path], sha: str) -> None:
        """An empty or option-like sha is rejected without running git."""
        _, project_dir = git_repo

        with patch(RUNNER) as runner:
            result = reset_hard(project_dir, sha)

        runner.assert_not_called()
        assert result["success"] is False
        assert result["error"]
        assert result["returncode"] is None

    def test_non_repo(self, tmp_path: Path) -> None:
        """A non-repository is an error result."""
        result = reset_hard(tmp_path, "HEAD")

        assert result["success"] is False
        assert result["error"]
        assert result["returncode"] is None
