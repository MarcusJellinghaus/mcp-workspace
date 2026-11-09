"""Disk cache for a repository's labels.

One file per repo, shared with mcp-coder and read on every call. The entry is
reloaded only when it is missing, invalid or expired, or on ``refresh=True``.
A rate-limited reload falls back to the existing entry; a failed fetch is
never saved.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, NamedTuple

from mcp_workspace.utils.timezone_utils import (
    format_for_cache,
    parse_iso_timestamp,
    utc_now,
)

from ..labels_manager import LabelData
from ._store import _save_cache_file, cache_file_path, is_expired, load_json, new_expiry
from .errors import GitHubRateLimitError, rate_limit_guard

if TYPE_CHECKING:
    # Type-only: see the import-cycle note in caching/__init__.py.
    from ..issues.manager import IssueManager

logger = logging.getLogger(__name__)

LABELS_CACHE_VERSION = 1

LABELS_MAX_AGE = timedelta(hours=24)

_SUFFIX = "labels"

_LABEL_FIELDS = ("name", "color", "description", "url")


class CachedLabels(NamedTuple):
    """Labels plus the footer line describing the cache state."""

    labels: list[LabelData]
    footer: str


class _Entry(NamedTuple):
    """A validated cache entry."""

    fetched_at: str
    labels: list[LabelData]
    raw: dict[str, Any]


def _valid_label(label: Any) -> bool:
    """Return True if ``label`` is a dict with every LabelData field as str."""
    return isinstance(label, dict) and all(
        isinstance(label.get(field), str) for field in _LABEL_FIELDS
    )


def _valid_entry(data: dict[str, Any]) -> _Entry | None:
    """Return the entry if ``fetched_at`` and every label are well-formed, else None.

    The file is shared with mcp-coder and consumers index every label field,
    so a partial entry counts as a miss.
    """
    fetched_at = data.get("fetched_at")
    labels = data.get("labels")
    if not isinstance(fetched_at, str) or not isinstance(labels, list):
        return None
    try:
        parse_iso_timestamp(fetched_at)
    except ValueError:
        return None
    if not all(_valid_label(label) for label in labels):
        return None
    return _Entry(fetched_at, labels, data)


def _footer(fetched_at: str, error: GitHubRateLimitError | None = None) -> str:
    """Build the footer line, marking it stale after a rate-limited refresh.

    Args:
        fetched_at: Timestamp of the cached entry.
        error: Rate-limit error from a failed refresh, if any.

    Returns:
        The footer naming when the labels were fetched.
    """
    footer = f"Label cache last updated {fetched_at}"
    if error is None:
        return footer
    if error.reset_at is None:
        return f"{footer} — refresh failed: rate limited (reset time unknown)"
    return (
        f"{footer} — refresh failed: rate limited until "
        f"{format_for_cache(error.reset_at)}"
    )


def get_cached_labels(manager: IssueManager, refresh: bool = False) -> CachedLabels:
    """Return the repo's labels from the disk cache, fetching them when needed.

    Args:
        manager: Issue manager of the repository; only ``repo_identifier`` and
            ``get_available_labels()`` are used.
        refresh: Refetch even when the cached entry is still valid.

    Returns:
        The labels and a footer naming when they were fetched.

    Raises:
        GitHubRateLimitError: If the fetch hit a rate limit and there is no
            cached entry to fall back to.
    """  # noqa: DOC502  # other fetch errors propagate unchanged
    path = cache_file_path(manager.repo_identifier, _SUFFIX)
    entry = _valid_entry(load_json(path, LABELS_CACHE_VERSION))
    now = utc_now()
    if entry is not None and not refresh and not is_expired(entry.raw, now):
        return CachedLabels(entry.labels, _footer(entry.fetched_at))

    try:
        with rate_limit_guard():
            labels = manager.get_available_labels()
    except GitHubRateLimitError as e:
        if entry is None:
            raise
        logger.debug(f"Label refresh rate limited, using cached labels: {e}")
        return CachedLabels(entry.labels, _footer(entry.fetched_at, e))

    fetched_at = format_for_cache(now)
    _save_cache_file(
        path,
        {
            "version": LABELS_CACHE_VERSION,
            "fetched_at": fetched_at,
            "expires_at": new_expiry(now, LABELS_MAX_AGE),
            "labels": labels,
        },
    )
    return CachedLabels(labels, _footer(fetched_at))
