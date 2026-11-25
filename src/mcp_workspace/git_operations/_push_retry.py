"""Retry a git push that GitHub answered with HTTP 500.

GitHub occasionally answers a push with HTTP 500 and accepts the same push
moments later. Only that failure is retried, and it is recognised from git's
stderr alone, never from the exit code: every other failure (rejection,
stale lease, authentication, timeout) reaches the caller after one attempt.

A push gets 3 attempts, waiting 5 s and then 15 s between them. Each retry
logs one WARNING, because a recovered 500 must stay visible (it marks the
Jenkins build unstable) rather than pass silently.
"""

import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

from git.exc import GitCommandError

from mcp_workspace.utils.url_credentials import scrub_credentials

from .core import logger

T = TypeVar("T")

_RETRY_WAITS: tuple[float, ...] = (5.0, 15.0)

_HTTP_500 = re.compile(
    r"\[remote rejected\] .*\(Internal Server Error\)"
    r"|The requested URL returned error: 500\b"
)


def _match_500(stderr: str | None) -> str | None:
    """Find the stderr line that shows a GitHub HTTP 500.

    The search is per line and not anchored to the line start, because
    GitPython decorates stderr with a leading ``stderr: '`` prefix.

    Returns:
        The first matching line, stripped, or None if no line matches.
    """
    for line in (stderr or "").splitlines():
        if _HTTP_500.search(line):
            return line.strip()
    return None


def retry_500(fn: Callable[..., T], *args: Any) -> T:
    """Call a push function, retrying it while GitHub answers HTTP 500.

    Handles both push mechanisms: GitPython raises ``GitCommandError``,
    ``run_git_timed`` returns a dict whose ``stderr`` is checked only when
    ``success`` is False. The last attempt runs outside the loop, so its
    exception or result reaches the caller unchanged.

    Returns:
        Whatever ``fn`` returns on the first attempt without an HTTP 500,
        or on the last attempt.

    Raises:
        GitCommandError: Re-raised at once unless it shows an HTTP 500;
            from the last attempt, raised as is.
    """
    for attempt, wait in enumerate(_RETRY_WAITS, start=1):
        try:
            result = fn(*args)
        except GitCommandError as e:
            line = _match_500(e.stderr)
            if line is None:
                raise
        else:
            line = None
            if isinstance(result, dict) and not result["success"]:
                line = _match_500(result["stderr"])
            if line is None:
                return result
        logger.warning(
            "git push got GitHub HTTP 500 (attempt %d of %d), retrying in %g s: %s",
            attempt,
            len(_RETRY_WAITS) + 1,
            wait,
            scrub_credentials(line),
        )
        time.sleep(wait)
    return fn(*args)
