"""Unit tests for the centralized PyGithub client factory."""

import io
import json
import logging
import time
from unittest.mock import patch

import pytest
import urllib3
from urllib3.util.retry import Retry

from mcp_workspace.github_operations._client import (
    GITHUB_REQUEST_TIMEOUT,
    GITHUB_RETRY_TOTAL,
    _LoggingGithubRetry,
    build_github_client,
)

MODULE = "mcp_workspace.github_operations._client"


def test_build_github_client_applies_timeout_retry_and_base_url() -> None:
    """build_github_client constructs Github with bounded timeout/retry."""
    with patch(f"{MODULE}.Github") as mock_github:
        client = build_github_client("tok", "https://api.github.com")

    mock_github.assert_called_once()
    call_kwargs = mock_github.call_args.kwargs
    assert call_kwargs["timeout"] == 10
    assert call_kwargs["base_url"] == "https://api.github.com"
    assert call_kwargs["retry"].total == 2
    assert client is mock_github.return_value


def test_factory_constants_are_load_bearing() -> None:
    """Guard the 30s single-call timeout math (10 x (1 + 2 retries))."""
    assert GITHUB_REQUEST_TIMEOUT == 10
    assert GITHUB_RETRY_TOTAL == 2


def _run(
    caplog: pytest.LogCaptureFixture, headers: dict[str, str], message: str = ""
) -> tuple[float, list[str], Retry]:
    """Run increment -> sleep on a 403 stub; return (slept, our messages, new retry)."""
    caplog.set_level(logging.INFO, logger=MODULE)
    body = io.BytesIO(json.dumps({"message": message}).encode())
    stub = urllib3.HTTPResponse(
        body=body, headers=headers, status=403, preload_content=False
    )
    new_retry = _LoggingGithubRetry(total=2).increment("GET", "/user", response=stub)
    with patch("urllib3.util.retry.time.sleep") as mock_sleep:
        new_retry.sleep(stub)
    slept = mock_sleep.call_args.args[0]
    return (
        slept,
        [r.getMessage() for r in caplog.records if r.name == MODULE],
        new_retry,
    )


def test_logging_retry_logs_primary_rate_limit_wait(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Primary rate limit: logs the wait until reset on our own logger."""
    headers = {
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": str(int(time.time()) + 600),
    }
    slept, messages, new_retry = _run(
        caplog, headers, "API rate limit exceeded for user ID 1."
    )

    assert 595 < slept <= 602
    assert len(messages) == 1
    assert "rate limit exhausted" in messages[0]
    assert f"{round(slept)}s" in messages[0]
    assert "resets" in messages[0]
    assert "(GET /user)" in messages[0]
    assert (
        type(new_retry) is _LoggingGithubRetry
    )  # pylint: disable=unidiomatic-typecheck


def test_logging_retry_logs_secondary_rate_limit_wait(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Secondary rate limit: logs the 60s secondary wait."""
    slept, messages, _ = _run(caplog, {}, "You have exceeded a secondary rate limit.")

    assert slept == 60
    assert len(messages) == 1
    assert "secondary rate limit" in messages[0]
    assert "60s" in messages[0]


def test_logging_retry_logs_retry_after_wait(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Retry-After header: logs the header-requested wait."""
    slept, messages, _ = _run(caplog, {"Retry-After": "120"})

    assert slept == 120
    assert len(messages) == 1
    assert "Retry-After" in messages[0]
    assert "120s" in messages[0]


@pytest.mark.parametrize("seconds", ["14", "15"])
def test_logging_retry_does_not_log_short_waits(
    caplog: pytest.LogCaptureFixture, seconds: str
) -> None:
    """Waits of 15s or less are not logged."""
    slept, messages, _ = _run(caplog, {"Retry-After": seconds})

    assert slept == int(seconds)
    assert not messages
