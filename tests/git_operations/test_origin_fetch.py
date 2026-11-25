"""Tests for fetching ``origin`` with one retry."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import git
import pytest
from git import Repo

from mcp_workspace.git_operations._subprocess_git import GitOutput
from mcp_workspace.git_operations.origin_fetch import (
    FETCH_ARGS,
    FetchOutcome,
    fetch_origin,
    has_origin_remote,
)

pytestmark = pytest.mark.git_integration

_RUN_TARGET = "mcp_workspace.git_operations.origin_fetch.run_git_timed"
_TIMEOUT_ERROR = "git fetch timed out after 10 s"


def _git(path: Path, *args: str) -> str:
    """Run a git command in ``path`` and return its stdout."""
    return str(git.Git(path).execute(["git", *args]))


def _ok() -> GitOutput:
    return GitOutput(success=True, error=None, returncode=0, stderr="", stdout="")


def _failed(stderr: str) -> GitOutput:
    return GitOutput(
        success=False,
        error="git fetch failed (exit 1)",
        returncode=1,
        stderr=stderr,
        stdout="",
    )


def _timed_out() -> GitOutput:
    return GitOutput(
        success=False, error=_TIMEOUT_ERROR, returncode=None, stderr=None, stdout=""
    )


@pytest.fixture
def repo_with_origin(tmp_path: Path) -> Path:
    """A repository whose ``origin`` is never contacted (run_git_timed is mocked)."""
    path = tmp_path / "repo"
    path.mkdir(parents=True, exist_ok=True)
    git.Git(path).init()
    _git(path, "remote", "add", "origin", "https://example.invalid/x.git")
    return path


class TestRealFetch:
    """Fetching from a real local origin."""

    def test_fetch_updates_tracking_ref_only(
        self, make_clone: Callable[[str], Path]
    ) -> None:
        """The fetch moves origin/main and leaves HEAD, branch, index, tree alone."""
        work = make_clone("work")
        up = make_clone("up")
        (up / "new.txt").write_text("new\n")
        _git(up, "add", "--", "new.txt")
        _git(up, "commit", "-q", "-m", "new")
        _git(up, "push", "-q", "origin", "HEAD:refs/heads/main")
        new_sha = _git(up, "rev-parse", "HEAD")

        readme = work / "README.md"
        readme.write_text("dirty\n")
        head_before = _git(work, "rev-parse", "HEAD")
        branch_before = _git(work, "symbolic-ref", "HEAD")

        outcome = fetch_origin(work)

        assert outcome == FetchOutcome(attempted=True, failure=None)
        assert _git(work, "rev-parse", "refs/remotes/origin/main") == new_sha
        assert _git(work, "rev-parse", "HEAD") == head_before
        assert _git(work, "symbolic-ref", "HEAD") == branch_before
        assert _git(work, "diff", "--cached", "--name-only") == ""
        assert readme.read_text() == "dirty\n"
        assert not (work / "new.txt").exists()


class TestSkipped:
    """Folders without an ``origin`` are not fetched."""

    def test_repo_without_origin(self, tmp_path: Path) -> None:
        path = tmp_path / "repo"
        Repo.init(path).close()
        with patch(_RUN_TARGET) as run:
            assert fetch_origin(path) == FetchOutcome(False, None)
        run.assert_not_called()
        assert has_origin_remote(path) is False

    def test_plain_folder(self, tmp_path: Path) -> None:
        path = tmp_path / "plain"
        path.mkdir()
        with patch(_RUN_TARGET) as run:
            assert fetch_origin(path) == FetchOutcome(False, None)
        run.assert_not_called()

    def test_missing_folder(self, tmp_path: Path) -> None:
        with patch(_RUN_TARGET) as run:
            assert fetch_origin(tmp_path / "missing") == FetchOutcome(False, None)
        run.assert_not_called()

    def test_folder_nested_in_checkout(self, origin_clone: Path) -> None:
        """A plain folder inside a checkout never fetches the parent repository."""
        nested = origin_clone / "nested"
        nested.mkdir()
        with patch(_RUN_TARGET) as run:
            assert fetch_origin(nested) == FetchOutcome(False, None)
        run.assert_not_called()

    def test_has_origin_remote_true(self, repo_with_origin: Path) -> None:
        assert has_origin_remote(repo_with_origin) is True


class TestRetry:
    """Retry and failure reporting, with ``run_git_timed`` mocked."""

    def test_failure_then_success(self, repo_with_origin: Path) -> None:
        with patch(_RUN_TARGET, side_effect=[_failed("fatal: x\nmore"), _ok()]) as run:
            assert fetch_origin(repo_with_origin) == FetchOutcome(True, None)
        assert run.call_count == 2

    def test_two_failures_report_first_stderr_line(
        self, repo_with_origin: Path
    ) -> None:
        with patch(
            _RUN_TARGET,
            side_effect=[_failed("fatal: x\nmore"), _failed("fatal: x\nmore")],
        ) as run:
            assert fetch_origin(repo_with_origin) == FetchOutcome(True, "fatal: x")
        assert run.call_count == 2

    def test_leading_blank_stderr_lines_are_skipped(
        self, repo_with_origin: Path
    ) -> None:
        with patch(_RUN_TARGET, return_value=_failed("\n  \nfatal: y\n")):
            assert fetch_origin(repo_with_origin) == FetchOutcome(True, "fatal: y")

    def test_empty_stderr_reports_error(self, repo_with_origin: Path) -> None:
        with patch(_RUN_TARGET, return_value=_failed("")) as run:
            outcome = fetch_origin(repo_with_origin)
        assert outcome == FetchOutcome(True, "git fetch failed (exit 1)")
        assert run.call_count == 2

    def test_timeout_is_not_retried(self, repo_with_origin: Path) -> None:
        with patch(_RUN_TARGET, return_value=_timed_out()) as run:
            assert fetch_origin(repo_with_origin) == FetchOutcome(True, _TIMEOUT_ERROR)
        assert run.call_count == 1

    def test_not_run_without_timeout_is_retried(self, repo_with_origin: Path) -> None:
        """A process that could not start is retried; only a timeout stops early."""
        not_run = GitOutput(
            success=False,
            error="git fetch could not run: boom",
            returncode=None,
            stderr=None,
            stdout="",
        )
        with patch(_RUN_TARGET, return_value=not_run) as run:
            outcome = fetch_origin(repo_with_origin)
        assert outcome == FetchOutcome(True, "git fetch could not run: boom")
        assert run.call_count == 2

    def test_called_with_fetch_args_and_default_timeout(
        self, repo_with_origin: Path
    ) -> None:
        run = MagicMock(return_value=_ok())
        with patch(_RUN_TARGET, run):
            fetch_origin(repo_with_origin)
        run.assert_called_once_with(repo_with_origin, *FETCH_ARGS, timeout=10.0)

    def test_custom_timeout_is_passed(self, repo_with_origin: Path) -> None:
        run = MagicMock(return_value=_ok())
        with patch(_RUN_TARGET, run):
            fetch_origin(repo_with_origin, timeout=3.5)
        run.assert_called_once_with(repo_with_origin, *FETCH_ARGS, timeout=3.5)

    def test_fetch_args_are_the_issue_command(self) -> None:
        assert FETCH_ARGS == (
            "-c",
            "maintenance.auto=false",
            "-c",
            "gc.auto=0",
            "fetch",
            "--quiet",
            "--no-recurse-submodules",
            "--no-prune",
            "origin",
        )
