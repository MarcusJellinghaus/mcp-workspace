"""Tests for GitHubRateLimitError conversion and rate_limit_guard."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from github.GithubException import GithubException, RateLimitExceededException
from requests.exceptions import RetryError

from mcp_workspace.github_operations.caching.errors import (
    GitHubRateLimitError,
    rate_limit_guard,
    to_rate_limit_error,
)
from tests.github_operations.conftest import make_retry_error

_RESET = int(time.time()) + 600


class TestToRateLimitError:
    """Tests for to_rate_limit_error."""

    @pytest.mark.parametrize(
        "exc",
        [
            RateLimitExceededException(
                403, {"message": "x"}, {"X-RateLimit-Reset": str(_RESET)}
            ),
            GithubException(429, {"message": "x"}, {"x-ratelimit-reset": str(_RESET)}),
            GithubException(
                403,
                {"message": "x"},
                {"X-RateLimit-Remaining": "0", "X-RATELIMIT-RESET": str(_RESET)},
            ),
        ],
    )
    def test_converted_with_reset_at(self, exc: GithubException) -> None:
        err = to_rate_limit_error(exc)
        assert isinstance(err, GitHubRateLimitError)
        assert err.reset_at == datetime.fromtimestamp(_RESET, tz=timezone.utc)

    @pytest.mark.parametrize(
        "exc",
        [
            RateLimitExceededException(403, {"message": "x"}, None),
            GithubException(429, {"message": "x"}, {}),
            GithubException(
                403,
                {"message": "x"},
                {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "soon"},
            ),
        ],
    )
    def test_converted_without_reset_at(self, exc: GithubException) -> None:
        err = to_rate_limit_error(exc)
        assert isinstance(err, GitHubRateLimitError)
        assert err.reset_at is None

    @pytest.mark.parametrize(
        "exc", [make_retry_error(403), make_retry_error(429), RetryError("x")]
    )
    def test_retry_error_converted(self, exc: RetryError) -> None:
        err = to_rate_limit_error(exc)
        assert isinstance(err, GitHubRateLimitError)
        assert err.reset_at is None

    @pytest.mark.parametrize(
        "exc",
        [
            make_retry_error(500),
            GithubException(404, {"message": "Not Found"}, {}),
            ValueError("x"),
        ],
    )
    def test_not_rate_limit_returns_none(self, exc: Exception) -> None:
        assert to_rate_limit_error(exc) is None

    def test_message_is_args_and_str(self) -> None:
        err = to_rate_limit_error(GithubException(429, {"message": "x"}, {}))
        assert err is not None
        assert err.args == (err.message,)
        assert str(err) == err.message == "GitHub rate limit exhausted"


class TestRateLimitGuard:
    """Tests for rate_limit_guard."""

    def test_rate_limit_converted_from_original(self) -> None:
        original = GithubException(429, {"message": "x"}, {})
        with pytest.raises(GitHubRateLimitError) as info:
            with rate_limit_guard():
                raise original
        assert info.value.__cause__ is original

    @pytest.mark.parametrize(
        "exc",
        [
            GithubException(404, {"message": "Not Found"}, {}),
            ValueError("x"),
        ],
    )
    def test_other_errors_reraised_unchanged(self, exc: Exception) -> None:
        with pytest.raises(type(exc)) as info:
            with rate_limit_guard():
                raise exc
        assert info.value is exc

    def test_already_converted_passes_through(self) -> None:
        err = GitHubRateLimitError("limit")
        with pytest.raises(GitHubRateLimitError) as info:
            with rate_limit_guard():
                raise err
        assert info.value is err

    def test_no_error_no_effect(self) -> None:
        with rate_limit_guard():
            value = 1
        assert value == 1


def test_exported_from_package() -> None:
    from mcp_workspace.github_operations import (
        GitHubRateLimitError as Exported,
    )  # pylint: disable=import-outside-toplevel

    assert Exported is GitHubRateLimitError
