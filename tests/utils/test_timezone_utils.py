"""Tests for mcp_workspace.utils.timezone_utils module."""

from datetime import UTC, datetime

from mcp_workspace.utils.timezone_utils import utc_now


def test_utc_now_returns_datetime() -> None:
    result = utc_now()
    assert isinstance(result, datetime)


def test_utc_now_is_timezone_aware() -> None:
    result = utc_now()
    assert result.tzinfo is not None


def test_utc_now_uses_utc_timezone() -> None:
    result = utc_now()
    assert result.tzinfo == UTC


def test_utc_now_returns_current_time() -> None:
    before = datetime.now(UTC)
    result = utc_now()
    after = datetime.now(UTC)
    assert before <= result <= after
