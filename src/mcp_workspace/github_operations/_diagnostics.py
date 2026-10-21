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
import re
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


_RETRY_STATUS_RE = re.compile(r"too many (\d{3}) error responses")


def _retry_error_status(exc: RetryError) -> int | None:
    """Return the HTTP status whose retries were exhausted, or None if unknown.

    requests wraps urllib3's `MaxRetryError`, whose `reason` is a
    `ResponseError` reading "too many <status> error responses".
    """
    max_retry_error = exc.args[0] if exc.args else None
    reason = getattr(max_retry_error, "reason", None)
    match = _RETRY_STATUS_RE.search(str(reason)) if reason is not None else None
    return int(match.group(1)) if match else None


def format_rate_limit_error(exc: BaseException) -> str | None:
    """Describe a GitHub rate-limit failure, or return None for any other error.

    A `RetryError` means GitHub's retry policy gave up; it retries 403 rate
    limits and 5xx server errors. Exhausted 403/429 retries count as a rate
    limit, exhausted 5xx retries do not, and an unknown status gets neutral
    wording. A `GithubException` counts as a rate limit when it is a
    `RateLimitExceededException`, has status 429, or reports
    `X-RateLimit-Remaining: 0`. Header lookup is case-insensitive.

    Returns:
        A message describing the rate limit, or None if the exception is not
        a rate-limit error.
    """
    if isinstance(exc, RetryError):
        status = _retry_error_status(exc)
        if status in (403, 429):
            return "GitHub rate limit: retries exhausted"
        if status is None:
            return (
                "GitHub request failed: retries exhausted "
                "(rate limit or server error)"
            )
        return None
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
