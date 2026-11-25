"""Tests for retrying a git push that GitHub answered with HTTP 500."""

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, call, patch

import pytest
from git.exc import GitCommandError

from mcp_workspace.git_operations._push_retry import _match_500, retry_500
from mcp_workspace.git_operations._subprocess_git import GitOutput
from mcp_workspace.git_operations.branches import delete_branch
from mcp_workspace.git_operations.remotes import (
    git_push,
    push_branch,
    push_current_branch,
)

MODULE = "mcp_workspace.git_operations._push_retry"
REMOTES = "mcp_workspace.git_operations.remotes"
BRANCHES = "mcp_workspace.git_operations.branches"

REJECTED_500 = (
    "remote: Internal Server Error\n"
    " ! [remote rejected] b -> b (Internal Server Error)\n"
    "error: failed to push some refs to 'https://github.com/o/r.git'"
)
FATAL_500 = (
    "remote: Internal Server Error\n"
    "fatal: unable to access 'https://github.com/o/r.git/': "
    "The requested URL returned error: 500"
)
NON_FAST_FORWARD = " ! [rejected]        b -> b (non-fast-forward)"
STALE_LEASE = " ! [rejected] b -> b (stale info)"
AUTH_FAILED = "fatal: Authentication failed for 'https://github.com/o/r.git/'"


def _git_error(stderr: str) -> GitCommandError:
    """Build a GitCommandError the way GitPython raises it for a failed push."""
    return GitCommandError(["git", "push", "origin", "b"], 1, stderr=stderr)


def _failed(stderr: str | None) -> dict[str, Any]:
    """Build a failed run_git_timed-like result."""
    return {
        "success": False,
        "error": "push failed",
        "returncode": 1 if stderr is not None else None,
        "stderr": stderr,
        "stdout": "",
    }


def _ok() -> dict[str, Any]:
    """Build a successful run_git_timed-like result."""
    return {
        "success": True,
        "error": None,
        "returncode": 0,
        "stderr": "",
        "stdout": "",
    }


class TestMatch500:
    """The stderr matcher recognises only GitHub HTTP 500 lines."""

    @pytest.mark.parametrize(
        ("stderr", "expected"),
        [
            (REJECTED_500, "! [remote rejected] b -> b (Internal Server Error)"),
            (
                FATAL_500,
                "fatal: unable to access 'https://github.com/o/r.git/': "
                "The requested URL returned error: 500",
            ),
            (
                " ! [remote rejected] b (Internal Server Error)",
                "! [remote rejected] b (Internal Server Error)",
            ),
        ],
        ids=["remote-rejected", "fatal-500", "remote-delete"],
    )
    def test_matches_500_line(self, stderr: str, expected: str) -> None:
        """A GitHub HTTP 500 line is returned stripped."""
        assert _match_500(stderr) == expected

    @pytest.mark.parametrize(
        "stderr", [REJECTED_500, FATAL_500], ids=["remote-rejected", "fatal-500"]
    )
    def test_matches_gitpython_decorated_stderr(self, stderr: str) -> None:
        """GitPython's decorated stderr form still matches."""
        decorated = _git_error(stderr).stderr
        line = _match_500(decorated)
        assert line is not None
        assert "Internal Server Error" in line or "error: 500" in line

    @pytest.mark.parametrize(
        "stderr",
        [
            "fatal: unable to access 'https://github.com/o/r.git/': "
            "The requested URL returned error: 5000",
            NON_FAST_FORWARD,
            None,
            "",
        ],
        ids=["error-5000", "non-fast-forward", "none", "empty"],
    )
    def test_no_match(self, stderr: str | None) -> None:
        """Anything other than a GitHub HTTP 500 yields None."""
        assert _match_500(stderr) is None


class TestRetry500GitPython:
    """retry_500 with a function that raises GitCommandError."""

    def test_500_then_success(self) -> None:
        """A single 500 is retried once after the first wait."""
        fn = MagicMock(side_effect=[_git_error(REJECTED_500), "ok"])
        with patch(f"{MODULE}.time.sleep") as sleep:
            assert retry_500(fn, "origin", "b") == "ok"
        assert fn.call_count == 2
        fn.assert_has_calls([call("origin", "b"), call("origin", "b")])
        sleep.assert_called_once_with(5.0)

    def test_500_every_attempt_raises_last_error(self) -> None:
        """After three 500s the third error reaches the caller."""
        errors = [_git_error(REJECTED_500) for _ in range(3)]
        fn = MagicMock(side_effect=errors)
        with patch(f"{MODULE}.time.sleep") as sleep:
            with pytest.raises(GitCommandError) as exc_info:
                retry_500(fn)
        assert exc_info.value is errors[2]
        assert fn.call_count == 3
        assert [c.args[0] for c in sleep.call_args_list] == [5.0, 15.0]


class TestRetry500Dict:
    """retry_500 with a run_git_timed-like function returning a dict."""

    def test_500_then_success(self) -> None:
        """A failed 500 result is retried and the success dict returned."""
        success = _ok()
        fn = MagicMock(side_effect=[_failed(FATAL_500), success])
        with patch(f"{MODULE}.time.sleep"):
            assert retry_500(fn) is success
        assert fn.call_count == 2

    def test_500_every_attempt_returns_last_result(self) -> None:
        """After three 500s the third failed result is returned."""
        results = [_failed(FATAL_500) for _ in range(3)]
        fn = MagicMock(side_effect=results)
        with patch(f"{MODULE}.time.sleep"):
            assert retry_500(fn) is results[2]
        assert fn.call_count == 3

    def test_success_first_call(self) -> None:
        """A successful first result is returned without retry."""
        success = _ok()
        fn = MagicMock(return_value=success)
        with patch(f"{MODULE}.time.sleep") as sleep:
            assert retry_500(fn) is success
        fn.assert_called_once()
        sleep.assert_not_called()


class TestNoRetry:
    """Failures other than HTTP 500 are passed through after one call."""

    @pytest.mark.parametrize(
        "stderr",
        [NON_FAST_FORWARD, STALE_LEASE, AUTH_FAILED],
        ids=["non-fast-forward", "stale-lease", "auth-failure"],
    )
    def test_git_error_raised_once(self, stderr: str) -> None:
        """A non-500 GitCommandError propagates on the first attempt."""
        error = _git_error(stderr)
        fn = MagicMock(side_effect=error)
        with patch(f"{MODULE}.time.sleep") as sleep:
            with pytest.raises(GitCommandError) as exc_info:
                retry_500(fn)
        assert exc_info.value is error
        fn.assert_called_once()
        sleep.assert_not_called()

    def test_timeout_result_returned_once(self) -> None:
        """A timeout result (stderr None) is returned without retry."""
        timeout = _failed(None)
        fn = MagicMock(return_value=timeout)
        with patch(f"{MODULE}.time.sleep") as sleep:
            assert retry_500(fn) is timeout
        fn.assert_called_once()
        sleep.assert_not_called()

    def test_other_exception_propagates(self) -> None:
        """An exception other than GitCommandError is not caught."""
        fn = MagicMock(side_effect=OSError("boom"))
        with patch(f"{MODULE}.time.sleep") as sleep:
            with pytest.raises(OSError, match="boom"):
                retry_500(fn)
        fn.assert_called_once()
        sleep.assert_not_called()


class TestRetryLogging:
    """Each retry logs one WARNING with credentials scrubbed."""

    def test_one_warning_per_retry(self, caplog: pytest.LogCaptureFixture) -> None:
        """Two 500s then success log exactly two warnings."""
        fn = MagicMock(
            side_effect=[_git_error(REJECTED_500), _git_error(REJECTED_500), "ok"]
        )
        with patch(f"{MODULE}.time.sleep"):
            with caplog.at_level(logging.WARNING):
                assert retry_500(fn) == "ok"
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2
        assert "attempt 1 of 3" in warnings[0].getMessage()
        assert "5 s" in warnings[0].getMessage()
        assert "attempt 2 of 3" in warnings[1].getMessage()
        assert "15 s" in warnings[1].getMessage()

    def test_warning_scrubs_credentials(self, caplog: pytest.LogCaptureFixture) -> None:
        """A URL with userinfo in the matched line is logged without it."""
        stderr = (
            "fatal: unable to access 'https://user:secret@github.com/o/r.git/': "
            "The requested URL returned error: 500"
        )
        fn = MagicMock(side_effect=[_failed(stderr), _ok()])
        with patch(f"{MODULE}.time.sleep"):
            with caplog.at_level(logging.WARNING):
                retry_500(fn)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "secret" not in warnings[0].getMessage()
        assert "error: 500" in warnings[0].getMessage()


# Copied from mcp_coder src/mcp_coder/workflow_steps/commit.py::_REJECTED_STATUS_LINE;
# git_push's error text must stay parseable by it.
_REJECTED_STATUS_LINE = re.compile(
    r"^[ \t]*! \[rejected\] .*\((?:fetch first|non-fast-forward)\)", re.MULTILINE
)

NON_FAST_FORWARD_PUSH = (
    "To https://github.com/o/r.git\n"
    " ! [rejected]        b -> b (non-fast-forward)\n"
    "error: failed to push some refs to 'https://github.com/o/r.git'"
)


def _origin() -> Mock:
    """Build an origin remote mock (``Mock(name=...)`` does not set ``.name``)."""
    origin = Mock()
    origin.name = "origin"
    return origin


def _run_with_repo(target: str, repo: Mock, fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run fn with the repo access in module ``target`` faked to yield repo."""

    @contextmanager
    def fake_safe_repo_context(_path: Path) -> Iterator[Mock]:
        yield repo

    with (
        patch(f"{target}.is_git_repository", return_value=True),
        patch(f"{target}.safe_repo_context", fake_safe_repo_context),
        patch(f"{MODULE}.time.sleep"),
    ):
        return fn(*args, **kwargs)


def _push_repo(*push_effects: Any) -> Mock:
    """Build a repo mock on branch ``b`` whose push yields push_effects."""
    repo = Mock()
    repo.active_branch.name = "b"
    repo.git.push.side_effect = list(push_effects)
    return repo


class TestGitPushRetry:
    """git_push retries a push that GitHub answered with HTTP 500."""

    def test_500_then_success(self) -> None:
        """A single 500 is retried and the push succeeds."""
        repo = _push_repo(_git_error(REJECTED_500), None)
        result = _run_with_repo(REMOTES, repo, git_push, Path("repo"))
        assert result == {"success": True, "error": None}
        assert repo.git.push.call_args_list == [call("origin", "b")] * 2

    def test_force_with_lease_500_then_success(self) -> None:
        """A force-with-lease push is retried with the same arguments."""
        repo = _push_repo(_git_error(REJECTED_500), None)
        result = _run_with_repo(
            REMOTES, repo, git_push, Path("repo"), force_with_lease=True
        )
        assert result == {"success": True, "error": None}
        assert (
            repo.git.push.call_args_list
            == [call("--force-with-lease", "origin", "b")] * 2
        )

    def test_500_every_attempt(self, caplog: pytest.LogCaptureFixture) -> None:
        """After three 500s the third error is reported and logged once."""
        errors = [_git_error(REJECTED_500) for _ in range(3)]
        repo = _push_repo(*errors)
        with caplog.at_level(logging.WARNING):
            result = _run_with_repo(REMOTES, repo, git_push, Path("repo"))
        assert result["success"] is False
        assert repo.git.push.call_count == 3
        assert result["error"].startswith("Git error during push: ")
        assert result["error"] == f"Git error during push: {errors[2]}"
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 1

    def test_500_then_non_fast_forward(self) -> None:
        """A rejection after a 500 stays parseable for mcp_coder."""
        repo = _push_repo(
            _git_error(REJECTED_500), _git_error(NON_FAST_FORWARD_PUSH), None
        )
        result = _run_with_repo(REMOTES, repo, git_push, Path("repo"))
        assert result["success"] is False
        assert repo.git.push.call_count == 2
        assert _REJECTED_STATUS_LINE.search(result["error"]) is not None

    def test_non_fast_forward_not_retried(self) -> None:
        """A non-fast-forward rejection is reported after one attempt."""
        repo = _push_repo(_git_error(NON_FAST_FORWARD_PUSH), None)
        result = _run_with_repo(REMOTES, repo, git_push, Path("repo"))
        assert result["success"] is False
        assert repo.git.push.call_count == 1


class TestPushBranchRetry:
    """push_branch retries a push that GitHub answered with HTTP 500."""

    @staticmethod
    def _push(repo: Mock) -> bool:
        repo.remotes = [_origin()]
        with patch(f"{REMOTES}.branch_exists", return_value=True):
            result: bool = _run_with_repo(
                REMOTES, repo, push_branch, "feature", Path("repo"), set_upstream=True
            )
        return result

    def test_500_then_success(self) -> None:
        """A single 500 is retried and the push succeeds."""
        repo = _push_repo(_git_error(REJECTED_500), None)
        assert self._push(repo) is True
        assert (
            repo.git.push.call_args_list
            == [call("--set-upstream", "origin", "feature")] * 2
        )

    def test_500_every_attempt(self) -> None:
        """After three 500s the push fails."""
        repo = _push_repo(*[_git_error(REJECTED_500) for _ in range(3)])
        assert self._push(repo) is False
        assert repo.git.push.call_count == 3


class TestDeleteBranchRetry:
    """delete_branch retries a remote delete that GitHub answered with HTTP 500."""

    @staticmethod
    def _delete(*push_effects: Any) -> tuple[bool, Mock]:
        repo = _push_repo(*push_effects)
        branches = [Mock(), Mock()]
        branches[0].name = "main"
        branches[1].name = "feature"
        repo.branches = branches
        repo.active_branch.name = "main"
        repo.remotes = [_origin()]
        repo.git.branch = Mock()
        result: bool = _run_with_repo(
            BRANCHES, repo, delete_branch, "feature", Path("repo"), delete_remote=True
        )
        return result, repo

    def test_500_then_success(self) -> None:
        """A single 500 is retried and the remote branch deleted."""
        result, repo = self._delete(_git_error(REJECTED_500), None)
        assert result is True
        assert (
            repo.git.push.call_args_list == [call("origin", "--delete", "feature")] * 2
        )

    def test_500_every_attempt_still_succeeds(self) -> None:
        """Remote deletion stays best-effort after three 500s."""
        result, repo = self._delete(*[_git_error(REJECTED_500) for _ in range(3)])
        assert result is True
        assert repo.git.push.call_count == 3


REFSPEC = "refs/heads/b:refs/heads/b"
SUBPROCESS_REJECTED_500 = (
    " ! [remote rejected] refs/heads/b -> b (Internal Server Error)"
)


def _git_output(
    success: bool,
    returncode: int | None,
    stderr: str | None,
    error: str | None = None,
) -> GitOutput:
    """Build a run_git_timed result."""
    return GitOutput(
        success=success,
        error=error if error is not None or success else "git push failed",
        returncode=returncode,
        stderr=stderr,
        stdout="",
    )


def _push_current(
    project_dir: Path, *results: GitOutput, force: bool = False
) -> tuple[Any, MagicMock]:
    """Run push_current_branch with run_git_timed yielding results."""
    run = MagicMock(side_effect=list(results))

    @contextmanager
    def fake_safe_repo_context(_path: Path) -> Iterator[Mock]:
        yield Mock()

    with (
        patch(f"{REMOTES}.is_git_repository", return_value=True),
        patch(f"{REMOTES}.get_current_branch_name", return_value="b"),
        patch(f"{REMOTES}.run_git_timed", run),
        patch(f"{REMOTES}.safe_repo_context", fake_safe_repo_context),
        patch(f"{REMOTES}._force_push_precondition", return_value=None),
        patch(f"{MODULE}.time.sleep"),
    ):
        return push_current_branch(project_dir, force=force), run


class TestPushCurrentBranchRetry:
    """push_current_branch retries a push that GitHub answered with HTTP 500."""

    def test_500_then_success(self) -> None:
        """A single 500 is retried with the same argv and the push succeeds."""
        project_dir = Path("repo")
        result, run = _push_current(
            project_dir,
            _git_output(False, 1, SUBPROCESS_REJECTED_500),
            _git_output(True, 0, ""),
        )
        assert result["success"] is True
        assert (
            run.call_args_list
            == [call(project_dir, "push", "-u", "origin", REFSPEC)] * 2
        )

    def test_force_500_then_success(self) -> None:
        """A force push is retried with the lease flags kept."""
        project_dir = Path("repo")
        result, run = _push_current(
            project_dir,
            _git_output(False, 128, FATAL_500),
            _git_output(True, 0, ""),
            force=True,
        )
        assert result["success"] is True
        expected = call(
            project_dir,
            "push",
            "-u",
            "--force-with-lease",
            "--force-if-includes",
            "origin",
            REFSPEC,
        )
        assert run.call_args_list == [expected] * 2

    def test_500_every_attempt_returns_last_result(self) -> None:
        """After three 500s the third result's stderr and returncode are returned."""
        last_stderr = f"{SUBPROCESS_REJECTED_500}\nattempt 3"
        result, run = _push_current(
            Path("repo"),
            _git_output(False, 1, SUBPROCESS_REJECTED_500),
            _git_output(False, 1, SUBPROCESS_REJECTED_500),
            _git_output(False, 128, last_stderr),
        )
        assert result["success"] is False
        assert result["stderr"] == last_stderr
        assert result["returncode"] == 128
        assert run.call_count == 3

    def test_timeout_not_retried(self) -> None:
        """A timeout result is returned as is after one attempt."""
        error = "git push timed out after 120 s"
        result, run = _push_current(
            Path("repo"), _git_output(False, None, None, error=error)
        )
        assert result == {
            "success": False,
            "error": error,
            "returncode": None,
            "stderr": None,
        }
        assert run.call_count == 1

    def test_stale_lease_not_retried(self) -> None:
        """A stale-lease rejection is returned after one attempt."""
        result, run = _push_current(
            Path("repo"), _git_output(False, 1, STALE_LEASE), force=True
        )
        assert result["success"] is False
        assert result["stderr"] == STALE_LEASE
        assert run.call_count == 1
