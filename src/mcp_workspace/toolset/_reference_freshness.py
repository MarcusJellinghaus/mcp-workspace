"""Throttled auto-fetch of reference projects, and the notes it produces.

Synchronous: called from the worker thread that also reads the reference
project, so the fetch and the read never block the event loop.
"""

import logging
import threading
import time
from pathlib import Path

from mcp_workspace.toolset._context import FetchRecord, WorkspaceContext
from mcp_workspace.utils.url_credentials import scrub_credentials

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_S = 10.0

# Exception types an error result keeps when notes are attached; any other
# type (e.g. GitCommandError) becomes ValueError.
_KEPT_ERROR_TYPES: tuple[type[Exception], ...] = (
    IsADirectoryError,
    FileNotFoundError,
    PermissionError,
    ValueError,
)


def _is_stale(ctx: WorkspaceContext, name: str) -> bool:
    """Return True if no fetch completed within the last interval."""
    record = ctx.reference_state.fetch_records.get(name)
    if record is None:
        return True
    interval_s = ctx.reference_fetch_interval_minutes * 60
    return time.monotonic() - record.completed_at >= interval_s


def mark_fetched(ctx: WorkspaceContext, name: str) -> None:
    """Record a successful fetch now (a fresh clone counts as one).

    Args:
        ctx: Context holding the fetch records.
        name: Reference project name.
    """
    ctx.reference_state.fetch_records[name] = FetchRecord(time.monotonic(), None)


def fetch_if_stale(ctx: WorkspaceContext, name: str, path: Path) -> None:
    """Fetch ``origin`` of a reference project if the last fetch is too old.

    The per-project lock is held for the fetch and its retry; readers queued
    behind it re-check staleness and use the fresh result. Never raises: an
    unexpected error on the fetch path (e.g. an unreadable git config) is
    recorded as a failed attempt, so it becomes a note instead of failing
    the caller's read.

    Args:
        ctx: Context holding the interval, fetch locks and fetch records.
        name: Reference project name.
        path: Local folder of the reference project.
    """
    if ctx.reference_fetch_interval_minutes == 0 or not _is_stale(ctx, name):
        return
    state = ctx.reference_state
    with state.fetch_locks.setdefault(name, threading.Lock()):
        if not _is_stale(ctx, name):
            return
        # Lazy import: keeps GitPython off the server startup import path
        from mcp_workspace.git_operations.origin_fetch import fetch_origin

        try:
            outcome = fetch_origin(path, timeout=FETCH_TIMEOUT_S)
        except Exception as exc:  # pylint: disable=broad-exception-caught  # a fetch failure never fails a read
            reason = _error_reason(exc)
            logger.warning("Auto-fetch of reference '%s' failed: %s", name, reason)
            state.fetch_records[name] = FetchRecord(time.monotonic(), reason)
            return
        if outcome.attempted:
            state.fetch_records[name] = FetchRecord(time.monotonic(), outcome.failure)


def _error_reason(exc: Exception) -> str:
    """Return the first non-empty line of ``exc``'s scrubbed message, else its type."""
    for line in scrub_credentials(str(exc)).splitlines():
        if line.strip():
            return line.strip()
    return type(exc).__name__


def fetch_failure_note(
    ctx: WorkspaceContext, name: str, where: str | None
) -> str | None:
    """Return the note for a failed last fetch, or None.

    Args:
        ctx: Context holding the interval and fetch records.
        name: Reference project name.
        where: What was read instead (e.g. "origin/main @ 03d1741"), or None
            when no ref is known.

    Returns:
        The note text, or None when auto-fetch is off or the last fetch did
        not fail.
    """
    record = ctx.reference_state.fetch_records.get(name)
    if (
        ctx.reference_fetch_interval_minutes == 0
        or record is None
        or record.failure is None
    ):
        return None
    suffix = f" — read {where}" if where else ""
    return f"[reference {name}: fetch failed ({record.failure}){suffix}]"


def fallback_note(name: str) -> str:
    """Return the note for a git repo without a usable origin default branch.

    Args:
        name: Reference project name.

    Returns:
        The note text.
    """
    return (
        f"[reference {name}: no usable origin default branch — read the local folder]"
    )


def with_notes(exc: BaseException, notes: list[str]) -> Exception:
    """Return a new error carrying ``exc``'s message followed by the notes.

    Args:
        exc: The original error.
        notes: Notes to append, one per line.

    Returns:
        An error of the same type for file and value errors, else ValueError.
    """
    text = f"{exc}\n" + "\n".join(notes)
    for cls in _KEPT_ERROR_TYPES:
        if isinstance(exc, cls):
            return cls(text)
    return ValueError(text)
