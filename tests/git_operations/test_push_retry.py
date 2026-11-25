"""Tests for retrying a git push that GitHub answered with HTTP 500."""

import logging
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from git.exc import GitCommandError

from mcp_workspace.git_operations._push_retry import _match_500, retry_500

MODULE = "mcp_workspace.git_operations._push_retry"

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
