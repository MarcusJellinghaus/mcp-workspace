"""Unit tests for `_diagnostics` helper module."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

import pytest
from github.GithubException import GithubException, RateLimitExceededExceedsMaxWait
from requests.exceptions import RetryError

from mcp_workspace.github_operations._diagnostics import (
    DIAGNOSTIC_HEADERS,
    extract_diagnostic_headers,
    extract_graphql_errors,
    format_rate_limit_error,
)
from tests.github_operations.conftest import make_retry_error


def _make_exception(headers: Any) -> GithubException:
    """Build a GithubException with the given headers attribute."""
    exc = GithubException(401, {"message": "Bad credentials"}, headers)
    return exc


class TestDiagnosticHeadersConstant:
    """Tests for the DIAGNOSTIC_HEADERS allow-list."""

    def test_diagnostic_headers_is_frozenset(self) -> None:
        assert isinstance(DIAGNOSTIC_HEADERS, frozenset)

    def test_diagnostic_headers_contains_expected_ten(self) -> None:
        expected = {
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
        assert set(DIAGNOSTIC_HEADERS) == expected


class TestExtractDiagnosticHeaders:
    """Tests for extract_diagnostic_headers()."""

    def test_none_headers_returns_empty_dict(self) -> None:
        exc = _make_exception(None)
        assert extract_diagnostic_headers(exc) == {}

    def test_empty_headers_returns_empty_dict(self) -> None:
        exc = _make_exception({})
        assert extract_diagnostic_headers(exc) == {}

    def test_all_listed_headers_returned_verbatim(self) -> None:
        headers = {
            "WWW-Authenticate": "Bearer",
            "X-OAuth-Scopes": "repo",
            "X-Accepted-OAuth-Scopes": "repo",
            "X-GitHub-Request-Id": "ABCD:1234",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Limit": "60",
            "Date": "Wed, 30 Apr 2026 12:00:00 GMT",
        }
        exc = _make_exception(headers)
        result = extract_diagnostic_headers(exc)
        assert result == headers

    def test_mixed_listed_and_unlisted_only_listed_returned(self) -> None:
        headers = {
            "X-GitHub-Request-Id": "ABCD:1234",
            "Set-Cookie": "session=abc",
            "X-Proxy-Foo": "bar",
            "WWW-Authenticate": "Bearer",
        }
        exc = _make_exception(headers)
        result = extract_diagnostic_headers(exc)
        assert result == {
            "X-GitHub-Request-Id": "ABCD:1234",
            "WWW-Authenticate": "Bearer",
        }

    def test_lowercase_keys_match_and_are_returned(self) -> None:
        headers = {
            "x-github-request-id": "ABCD:1234",
            "www-authenticate": "Bearer",
        }
        exc = _make_exception(headers)
        result = extract_diagnostic_headers(exc)
        assert result == {
            "x-github-request-id": "ABCD:1234",
            "www-authenticate": "Bearer",
        }

    def test_mixed_case_keys_match_and_are_returned(self) -> None:
        headers = {
            "X-GitHub-Request-Id": "ABCD:1234",
            "X-RateLimit-Remaining": "5",
        }
        exc = _make_exception(headers)
        result = extract_diagnostic_headers(exc)
        assert result == headers

    def test_unlisted_headers_excluded(self) -> None:
        headers = {
            "Set-Cookie": "session=abc",
            "X-Proxy-Foo": "bar",
            "Content-Type": "application/json",
        }
        exc = _make_exception(headers)
        result = extract_diagnostic_headers(exc)
        assert result == {}


def _hhmm(reset: int) -> str:
    """Format a reset epoch as the HH:MM UTC string the helper emits."""
    return datetime.fromtimestamp(reset, tz=timezone.utc).strftime("%H:%M")


class TestFormatRateLimitError:
    """Tests for format_rate_limit_error()."""

    @pytest.mark.parametrize(
        "exc",
        [
            GithubException(403, {"message": "Forbidden"}, {}),
            GithubException(500, {"message": "Server Error"}, {}),
            ValueError("x"),
            ConnectionError(),
        ],
    )
    def test_non_rate_limit_returns_none(self, exc: BaseException) -> None:
        assert format_rate_limit_error(exc) is None

    def test_remaining_zero_lowercase_headers(self) -> None:
        reset = int(time.time()) + 600
        exc = GithubException(
            403,
            {"message": "API rate limit exceeded"},
            {
                "x-ratelimit-remaining": "0",
                "x-ratelimit-resource": "core",
                "x-ratelimit-reset": str(reset),
            },
        )
        msg = format_rate_limit_error(exc)
        assert msg is not None
        assert "`core`" in msg
        assert f"resets at {_hhmm(reset)} UTC" in msg
        assert re.search(r"in \d+ min", msg)

    def test_exceeds_max_wait_original_casing(self) -> None:
        reset = int(time.time()) + 600
        exc = RateLimitExceededExceedsMaxWait(
            403,
            {"message": "API rate limit exceeded"},
            {
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Resource": "core",
                "X-RateLimit-Reset": str(reset),
            },
            wait=600,
        )
        msg = format_rate_limit_error(exc)
        assert msg is not None
        assert "`core`" in msg
        assert f"resets at {_hhmm(reset)} UTC" in msg
        assert re.search(r"in \d+ min", msg)

    def test_429_with_resource_only(self) -> None:
        exc = GithubException(
            429, {"message": "Too Many Requests"}, {"x-ratelimit-resource": "search"}
        )
        msg = format_rate_limit_error(exc)
        assert msg is not None
        assert "`search`" in msg
        assert "resets" not in msg

    def test_rate_limit_without_headers(self) -> None:
        exc = RateLimitExceededExceedsMaxWait(403, {"message": "x"}, None)
        assert format_rate_limit_error(exc) == "GitHub rate limit exhausted"

    @pytest.mark.parametrize("status", [403, 429])
    def test_retry_error_on_rate_limit_status(self, status: int) -> None:
        assert (
            format_rate_limit_error(make_retry_error(status))
            == "GitHub rate limit: retries exhausted"
        )

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_retry_error_on_server_error_returns_none(self, status: int) -> None:
        assert format_rate_limit_error(make_retry_error(status)) is None

    def test_retry_error_without_status_is_neutral(self) -> None:
        assert format_rate_limit_error(RetryError("x")) == (
            "GitHub request failed: retries exhausted (rate limit or server error)"
        )


class TestExtractGraphqlErrors:
    """Tests for extract_graphql_errors()."""

    def test_single_error_with_type(self) -> None:
        body = {
            "errors": [
                {"type": "FORBIDDEN", "message": "Resource not accessible"},
            ]
        }
        assert extract_graphql_errors(body) == [
            ("FORBIDDEN", "Resource not accessible")
        ]

    def test_single_error_without_type(self) -> None:
        body = {"errors": [{"message": "Field 'x' doesn't exist on type 'Y'"}]}
        assert extract_graphql_errors(body) == [
            (None, "Field 'x' doesn't exist on type 'Y'")
        ]

    def test_three_errors_preserve_source_order(self) -> None:
        body = {
            "errors": [
                {"type": "FORBIDDEN", "message": "first"},
                {"message": "second"},
                {"type": "RATE_LIMITED", "message": "third"},
            ]
        }
        assert extract_graphql_errors(body) == [
            ("FORBIDDEN", "first"),
            (None, "second"),
            ("RATE_LIMITED", "third"),
        ]

    def test_partial_data_body_errors_parsed_and_data_ignored(self) -> None:
        body = {
            "data": {"repository": {"pullRequest": None}},
            "errors": [
                {
                    "type": "FORBIDDEN",
                    "path": ["repository", "pullRequest"],
                    "message": "Resource not accessible by integration",
                }
            ],
        }
        assert extract_graphql_errors(body) == [
            ("FORBIDDEN", "Resource not accessible by integration")
        ]

    @pytest.mark.parametrize(
        "body",
        [
            "raw text",
            None,
            [],
            42,
            {"message": "boom"},
            {"errors": "nope"},
            {"errors": {"message": "x"}},
            {"errors": None},
            {"errors": []},
            {"errors": ["a", None, 42]},
        ],
    )
    def test_unusable_input_returns_empty_list(self, body: Any) -> None:
        assert extract_graphql_errors(body) == []

    @pytest.mark.parametrize(
        "entry",
        [
            {},
            {"message": 42},
            {"message": None},
            {"message": "   "},
            {"message": ""},
            {"type": 42},
            {"type": "   "},
            {"type": None, "message": ""},
            {"path": ["repository"]},
        ],
    )
    def test_entries_without_type_or_message_are_skipped(self, entry: Any) -> None:
        assert extract_graphql_errors({"errors": [entry]}) == []

    @pytest.mark.parametrize(
        "entry",
        [
            {"type": "RATE_LIMITED"},
            {"type": "RATE_LIMITED", "message": None},
            {"type": "RATE_LIMITED", "message": "   "},
            {"type": "RATE_LIMITED", "message": 42},
        ],
    )
    def test_type_without_usable_message_is_kept(self, entry: Any) -> None:
        assert extract_graphql_errors({"errors": [entry]}) == [("RATE_LIMITED", None)]

    def test_non_str_type_becomes_none(self) -> None:
        body = {"errors": [{"type": 42, "message": "x"}]}
        assert extract_graphql_errors(body) == [(None, "x")]

    def test_mixed_valid_and_invalid_entries_returns_only_valid(self) -> None:
        body = {
            "errors": [
                "not a dict",
                {"type": "FORBIDDEN"},
                {"type": "NOT_FOUND", "message": "Could not resolve to a PullRequest"},
                {"message": "   "},
                None,
            ]
        }
        assert extract_graphql_errors(body) == [
            ("FORBIDDEN", None),
            ("NOT_FOUND", "Could not resolve to a PullRequest"),
        ]

    def test_multiline_message_returned_verbatim(self) -> None:
        message = "line one\nline two    with   spaces"
        body = {"errors": [{"message": message}]}
        assert extract_graphql_errors(body) == [(None, message)]
