"""Timezone utilities for datetime operations.

This module provides utilities for:
- Parsing ISO 8601 timestamps with timezone awareness
- Converting between timezones consistently
- Formatting timestamps for different APIs (GitHub, etc.)
- Handling timezone-naive and timezone-aware datetimes safely

All functions in this module ensure consistent UTC-based handling
to prevent timezone conversion bugs.
"""

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


def parse_iso_timestamp(timestamp_str: str) -> datetime:
    """Parse ISO 8601 timestamp string into timezone-aware datetime in UTC.

    Handles various ISO 8601 formats:
    - "2026-01-03T23:36:14.620992+01:00" (with timezone offset)
    - "2026-01-03T23:36:14Z" (UTC with Z suffix)
    - "2026-01-03T23:36:14" (naive, assumed UTC)
    - "2026-01-03T23:36:14.620992Z" (UTC with microseconds)

    Args:
        timestamp_str: ISO 8601 formatted timestamp string

    Returns:
        Timezone-aware datetime in UTC

    Raises:
        ValueError: If timestamp format is invalid
    """
    if not timestamp_str:
        raise ValueError("Timestamp string cannot be empty")

    try:
        # Handle Z suffix (UTC indicator)
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"

        # Parse with fromisoformat (handles timezone offsets)
        parsed_dt = datetime.fromisoformat(timestamp_str)

        # If naive (no timezone), assume UTC
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=UTC)
        else:
            # Convert to UTC if not already
            parsed_dt = parsed_dt.astimezone(UTC)

        return parsed_dt

    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid ISO timestamp format '{timestamp_str}': {e}") from e


def now_utc() -> datetime:
    """Get current time as timezone-aware datetime in UTC.

    Returns:
        Current time in UTC timezone
    """
    return datetime.now(UTC)


def format_for_cache(dt: datetime) -> str:
    """Format datetime for cache storage with timezone info.

    Args:
        dt: Timezone-aware datetime

    Returns:
        ISO 8601 string with timezone offset

    Raises:
        ValueError: If datetime is timezone-naive
    """
    if dt.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")

    return dt.isoformat()


def is_within_duration(
    timestamp: datetime,
    duration_seconds: float,
    reference_time: datetime | None = None,
) -> bool:
    """Check if a timestamp is within a duration from a reference time.

    Args:
        timestamp: The timestamp to check (timezone-aware recommended)
        duration_seconds: Duration in seconds
        reference_time: Reference time (timezone-aware). If None, uses current UTC time.

    Returns:
        True if timestamp is within duration from reference_time
    """
    if reference_time is None:
        reference_time = now_utc()

    elapsed = (reference_time - timestamp).total_seconds()
    return abs(elapsed) <= duration_seconds
