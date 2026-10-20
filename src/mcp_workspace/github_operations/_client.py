"""Centralized PyGithub client factory.

All PyGithub ``Github`` instances are created through ``build_github_client`` so
the timeout/retry policy lives in exactly one place and cannot drift across the
individual call sites.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from github import Auth, Github, GithubRetry

if TYPE_CHECKING:
    from urllib3 import BaseHTTPResponse

logger = logging.getLogger(__name__)

GITHUB_REQUEST_TIMEOUT = 10
GITHUB_RETRY_TOTAL = 2


class _LoggingGithubRetry(GithubRetry):
    """GithubRetry that logs any sleep longer than 15s on our own logger."""

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

    timeout=10 with GithubRetry(total=2) gives ~30s worst case on an
    unreachable host (1 initial + 2 retries). total=2 also caps 403
    secondary-rate-limit backoff to 2 attempts — deliberate, do NOT raise back.

    Args:
        token: GitHub personal access token.
        base_url: API base URL (e.g. ``https://api.github.com`` or a GHE host).

    Returns:
        A configured ``github.Github`` instance.
    """
    return Github(
        auth=Auth.Token(token),
        base_url=base_url,
        timeout=GITHUB_REQUEST_TIMEOUT,
        retry=GithubRetry(total=GITHUB_RETRY_TOTAL),
    )
