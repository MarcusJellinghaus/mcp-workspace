"""Centralized PyGithub client factory.

All PyGithub ``Github`` instances are created through ``build_github_client`` so
the timeout/retry policy lives in exactly one place and cannot drift across the
individual call sites.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from github import Auth, Github, GithubRetry

from mcp_workspace import config
from mcp_workspace.traffic_log import error_status, log_request

if TYPE_CHECKING:
    from types import TracebackType
    from typing import Self

    from urllib3 import BaseHTTPResponse
    from urllib3.connectionpool import ConnectionPool
    from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

GITHUB_REQUEST_TIMEOUT = 10
GITHUB_RETRY_TOTAL = 2
GITHUB_MAX_RATE_LIMIT_WAIT = 60

_warned_missing = False


class _LoggingGithubRetry(GithubRetry):
    """GithubRetry that logs long sleeps and writes traffic-log retry lines.

    Any sleep longer than 15s is logged on our own logger. When the traffic
    log is on, each retried attempt writes one ``retry ...`` line.
    """

    def __init__(self, *, api_host: str | None = None, **kwargs: Any) -> None:
        """Remember the API host so retry lines can redact foreign-host queries."""
        self.api_host = api_host
        super().__init__(**kwargs)

    def new(self, **kw: Any) -> Self:
        """Carry ``api_host`` into the copy urllib3 makes on every ``increment``.

        Returns:
            The new retry object, with ``api_host`` preserved.
        """
        kw["api_host"] = self.api_host
        return super().new(**kw)

    def increment(  # type: ignore[override]  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        method: str | None = None,
        url: str | None = None,
        response: BaseHTTPResponse | None = None,
        error: Exception | None = None,
        _pool: ConnectionPool | None = None,
        _stacktrace: TracebackType | None = None,
    ) -> Retry:
        """Write a ``retry`` traffic line when another attempt follows.

        If ``super().increment`` raises, nothing is written: the exception
        leaves ``__requestRaw`` and the traffic-log wrapper writes ``ERR``.

        Returns:
            The retry object from ``super().increment``.
        """
        new_retry = super().increment(
            method, url, response, error, _pool, _stacktrace  # type: ignore[arg-type]
        )
        if response is not None:
            status, headers = f"retry {response.status}", response.headers
        else:
            status, headers = f"retry {type(error).__name__}", None
        logged_url = url or "-"
        # urllib3 passes path + query only; a pool for another host (the 302
        # hop to a signed blob URL) carries a SAS signature in the query.
        if (
            _pool is not None
            and self.api_host is not None
            and _pool.host != self.api_host
        ):
            logged_url = logged_url.split("?", 1)[0]
        log_request(method or "-", logged_url, status, headers, None)
        return new_retry

    def sleep(self, response: BaseHTTPResponse | None = None) -> None:
        """Log the upcoming wait if it exceeds 15s, then sleep as urllib3 would.

        Computes the wait the same way ``Retry.sleep`` does: a truthy
        ``Retry-After`` wins, otherwise the backoff that
        ``GithubRetry.increment`` patched onto this instance.
        """
        retry_after = (
            self.get_retry_after(response)
            if self.respect_retry_after_header and response
            else None
        )
        wait = retry_after or self.get_backoff_time()
        if wait > 15:
            headers = response.headers if response is not None else {}
            seconds = round(wait)
            if "Retry-After" in headers:
                msg = (
                    f"GitHub requested a retry after {seconds}s "
                    "(Retry-After header), waiting"
                )
            elif headers.get("X-RateLimit-Remaining") == "0":
                msg = (
                    "GitHub REST rate limit exhausted for this token, "
                    f"waiting {seconds}s for the quota to reset"
                )
                reset = headers.get("X-RateLimit-Reset", "")
                if reset.isdigit():
                    reset_at = datetime.fromtimestamp(int(reset), timezone.utc)
                    msg += f" (resets {reset_at.strftime('%H:%M:%S')} UTC)"
            else:
                msg = (
                    f"GitHub secondary rate limit hit, waiting {seconds}s "
                    "before retrying"
                )
            if self.history:
                last = self.history[-1]
                msg += f" ({last.method} {last.url})"
            logger.info(msg)
        super().sleep(response)


def build_github_client(token: str, base_url: str) -> Github:
    """Create a PyGithub client with bounded timeout/retry.

    timeout=10 with total=2 gives ~30s worst case on an unreachable host
    (1 initial + 2 retries). total=2 also caps 403 secondary-rate-limit
    retries to 2 attempts — deliberate, do NOT raise back. Rate-limit waits
    are not capped by the timeout but by ``max_rate_limit_wait=60``: a
    primary-limit wait longer than 60s (until the quota resets, up to 1h)
    raises ``RateLimitExceededExceedsMaxWait`` immediately instead of
    waiting. The cap must stay >= ``secondary_rate_wait`` (60s) so a
    secondary limit still waits. ``_LoggingGithubRetry`` logs long waits.
    When the traffic log is on, every HTTP hop also writes one traffic line.

    Args:
        token: GitHub personal access token.
        base_url: API base URL (e.g. ``https://api.github.com`` or a GHE host).

    Returns:
        A configured ``github.Github`` instance.
    """
    client = Github(
        auth=Auth.Token(token),
        base_url=base_url,
        timeout=GITHUB_REQUEST_TIMEOUT,
        retry=_LoggingGithubRetry(
            total=GITHUB_RETRY_TOTAL,
            max_rate_limit_wait=GITHUB_MAX_RATE_LIMIT_WAIT,
            api_host=urlsplit(base_url).hostname,
        ),
    )
    if config.get_traffic_log_dir() is not None:
        _install_traffic_log(client)
    return client


def _install_traffic_log(client: Github) -> None:
    """Wrap this client's ``Requester.__requestRaw`` so each HTTP hop writes one line.

    The wrapper is an instance attribute, so PyGithub's own recursive
    ``self.__requestRaw(...)`` calls for 202/301/302 hops pass it again.
    """
    global _warned_missing  # pylint: disable=global-statement
    requester = client.requester
    original = getattr(requester, "_Requester__requestRaw", None)
    if original is None:
        if not _warned_missing:
            _warned_missing = True
            logger.warning("traffic log disabled: PyGithub internals changed")
        return

    def wrapper(
        cnx: Any, verb: str, url: str, *args: Any, **kwargs: Any
    ) -> tuple[int, dict[str, Any], Any]:
        # PyGithub passes a non-None cnx only for a host other than base_url
        # (__customConnection, e.g. the 302 hop to a signed blob URL); drop
        # that hop's query (SAS signature).
        logged_url = url.split("?", 1)[0] if cnx is not None else url
        start = time.monotonic()
        try:
            status, headers, output = original(cnx, verb, url, *args, **kwargs)
        except Exception as exc:
            if not getattr(exc, "_traffic_logged", False):
                log_request(
                    verb,
                    logged_url,
                    error_status(exc),
                    getattr(exc, "headers", None),
                    start,
                )
                try:
                    setattr(exc, "_traffic_logged", True)
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
            raise
        log_request(verb, logged_url, str(status), headers, start)
        return status, headers, output

    setattr(requester, "_Requester__requestRaw", wrapper)
