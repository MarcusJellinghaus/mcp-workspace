"""Private helpers for extracting diagnostic information from GitHub failures.

Covers both `GithubException` objects and raw response bodies. Used by
failure-path DEBUG logging across the `github_operations` package to produce
consistent, allow-listed header dumps without leaking secrets or proxy noise,
to pull human-readable reasons out of GraphQL error payloads, and to recognise
and describe GitHub rate-limit failures. This module is private to the
package; only `format_rate_limit_error` and `RetryError` are re-exported via
`github_operations/__init__.py`.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any

from github.GithubException import GithubException, RateLimitExceededException
from requests.exceptions import RetryError as RetryError  # re-exported

DIAGNOSTIC_HEADERS: frozenset[str] = frozenset(
    {
        "WWW-Authenticate",
        "X-OAuth-Scopes",
        "X-Accepted-OAuth-Scopes",
        "X-GitHub-Request-Id",
        "X-RateLimit-Remaining",
        "X-RateLimit-Limit",
        "X-RateLimit-Reset",
        "X-RateLimit-Used",
        "X-RateLimit-Resource",
        "Date",
    }
)


def extract_diagnostic_headers(exc: GithubException) -> dict[str, str]:
    """Return only allow-listed headers from `exc.headers` (case-insensitive lookup).

    Original key casing from `exc.headers` is preserved in the output. Returns
    an empty dict when no headers are present or none match the allow-list.
    """
    headers = exc.headers
    if not headers:
        return {}
    allow_lower = {h.lower() for h in DIAGNOSTIC_HEADERS}
    return {k: v for k, v in headers.items() if k.lower() in allow_lower}


def format_rate_limit_error(exc: BaseException) -> str | None:
    """Describe a GitHub rate-limit failure, or return None for any other error.

    A `RetryError` means urllib3 gave up retrying (GitHub's retry policy only
    retries rate-limit and server responses). A `GithubException` counts as a
    rate limit when it is a `RateLimitExceededException`, has status 429, or
    reports `X-RateLimit-Remaining: 0`. Header lookup is case-insensitive.

    Returns:
        A message describing the rate limit, or None if the exception is not
        a rate-limit error.
    """
    if isinstance(exc, RetryError):
        return "GitHub rate limit: retries exhausted"
    if not isinstance(exc, GithubException):
        return None
    headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
    if not (
        isinstance(exc, RateLimitExceededException)
        or exc.status == 429
        or headers.get("x-ratelimit-remaining") == "0"
    ):
        return None
    resource = headers.get("x-ratelimit-resource")
    msg = (
        f"GitHub `{resource}` rate limit exhausted"
        if resource
        else "GitHub rate limit exhausted"
    )
    reset = headers.get("x-ratelimit-reset")
    if reset and reset.isdigit():
        reset_epoch = int(reset)
        reset_at = datetime.fromtimestamp(reset_epoch, tz=timezone.utc)
        minutes = max(0, math.ceil((reset_epoch - time.time()) / 60))
        msg += f"; resets at {reset_at:%H:%M} UTC (in {minutes} min)"
    return msg


def _usable_str(value: Any) -> str | None:
    """Return `value` when it is a non-blank string, else None."""
    if isinstance(value, str) and value.strip():
        return value
    return None


def extract_graphql_errors(body: Any) -> list[tuple[str | None, str | None]]:
    """Return (type, message) pairs from a GraphQL response body's `errors` array.

    Parses defensively at every level: `body` may not be a dict, `errors` may
    not be a list, and entries may not be dicts. An entry is usable when it
    carries a non-blank string `type`, a non-blank string `message`, or both;
    either element is `None` when missing or unusable. A type-only entry such
    as `{"type": "RATE_LIMITED"}` still names a real failure, so it is kept.
    Only entries with neither are skipped. Messages are returned verbatim;
    presentation is the caller's job.

    Returns:
        Pairs in source order, or an empty list for any unusable input.
    """
    if not isinstance(body, dict):
        return []
    errors = body.get("errors")
    if not isinstance(errors, list):
        return []
    pairs: list[tuple[str | None, str | None]] = []
    for entry in errors:
        if not isinstance(entry, dict):
            continue
        err_type = _usable_str(entry.get("type"))
        message = _usable_str(entry.get("message"))
        if err_type is None and message is None:
            continue
        pairs.append((err_type, message))
    return pairs
