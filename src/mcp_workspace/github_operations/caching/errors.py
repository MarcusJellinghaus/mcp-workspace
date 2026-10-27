"""Rate-limit error raised by the GitHub caches.

A rate-limit failure is recognised by one rule: ``format_rate_limit_error(exc)
is not None``. That includes a ``RetryError`` with unknown status, on purpose.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from github.GithubException import GithubException

from .._diagnostics import format_rate_limit_error


class GitHubRateLimitError(Exception):
    """GitHub rate limit hit; the caller should stop this run. Nothing was cached."""

    def __init__(self, message: str, reset_at: datetime | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.reset_at = reset_at


def _reset_at(exc: BaseException) -> datetime | None:
    """Return the ``X-RateLimit-Reset`` time of a GithubException, else None."""
    if not isinstance(exc, GithubException):
        return None
    headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
    reset = headers.get("x-ratelimit-reset")
    if reset and reset.isdigit():
        return datetime.fromtimestamp(int(reset), tz=timezone.utc)
    return None


def to_rate_limit_error(exc: BaseException) -> GitHubRateLimitError | None:
    """Return a GitHubRateLimitError for a rate-limit exc, else None."""
    msg = format_rate_limit_error(exc)
    if msg is None:
        return None
    return GitHubRateLimitError(msg, _reset_at(exc))


@contextmanager
def rate_limit_guard() -> Iterator[None]:
    """Re-raise any rate-limit exception as GitHubRateLimitError (``from exc``)."""
    try:
        yield
    except Exception as e:
        if (rl := to_rate_limit_error(e)) is not None:
            raise rl from e
        raise
