"""Cache file I/O helpers for the issue cache.

This module provides:
- CacheData TypedDict for cache structure
- Cache file operations (load, save, get path)
- Cache metrics logging
"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, NotRequired, Optional, TypedDict

from mcp_coder_utils.user_app_data import get_user_app_data_dir

from mcp_workspace.utils.repo_identifier import RepoIdentifier

from .types import IssueData

logger = logging.getLogger(__name__)

# Delay before the single os.replace retry in _save_cache_file.
_REPLACE_RETRY_DELAY_SECONDS: float = 0.1


class CacheData(TypedDict):
    """Type definition for coordinator issue cache structure.

    Attributes:
        last_checked: ISO 8601 timestamp of last cache refresh, or None if never checked
        last_full_refresh: ISO 8601 timestamp of last successful full refresh, or None
        updates_covered_through: ISO 8601 data cursor (max observed issue
            ``updated_at``) used as the ``since`` floor for incremental refreshes,
            or None if never set (old-shape caches). Distinct from
            ``last_checked`` (wall-clock poll time).
        cached_at: Sidecar map ``{issue_number: ISO 8601 timestamp}`` recording
            when each cached entry was last written. Cache-level metadata, never
            a field on IssueData.
        version: Cache-schema version for safe migrations, or None if unset.
        issues: Dictionary mapping issue number (as string) to IssueData
    """

    last_checked: Optional[str]
    last_full_refresh: NotRequired[Optional[str]]
    updates_covered_through: NotRequired[Optional[str]]
    cached_at: NotRequired[Dict[str, str]]
    version: NotRequired[Optional[int]]
    issues: Dict[str, IssueData]


def _load_cache_file(cache_file_path: Path) -> CacheData:
    """Load cache file or return empty cache structure.

    Surfaces the schema fields with safe defaults on every return path, so
    callers always receive a fully-shaped ``CacheData``. Old-shape files (no
    ``updates_covered_through`` / ``version``) load with those set to None and
    ``cached_at`` defaulting to an empty dict, which is the precondition for the
    self-healing full refresh.

    Args:
        cache_file_path: Path to cache file

    Returns:
        CacheData with ``last_checked``, ``last_full_refresh``,
        ``updates_covered_through``, ``cached_at``, ``version`` and ``issues``.
        Returns an empty structure (new fields defaulted) on missing files,
        invalid structure or load errors.
    """
    empty: CacheData = {
        "last_checked": None,
        "last_full_refresh": None,
        "updates_covered_through": None,
        "cached_at": {},
        "version": None,
        "issues": {},
    }
    try:
        if not cache_file_path.exists():
            return empty

        with cache_file_path.open("r") as f:
            data = json.load(f)

        # Validate structure
        if not isinstance(data, dict) or "issues" not in data:
            logger.warning(f"Invalid cache structure in {cache_file_path}, recreating")
            return empty

        # Return as CacheData since we validated the structure
        return {
            "last_checked": data.get("last_checked"),
            "last_full_refresh": data.get("last_full_refresh"),
            "updates_covered_through": data.get("updates_covered_through"),
            "cached_at": data.get("cached_at", {}),
            "version": data.get("version"),
            "issues": data["issues"],
        }

    except (json.JSONDecodeError, OSError, PermissionError) as e:
        logger.warning(f"Cache load error for {cache_file_path}: {e}, starting fresh")
        return empty


def _log_cache_metrics(action: str, repo_name: str, **kwargs: Any) -> None:
    """Log detailed cache performance metrics at DEBUG level.

    Args:
        action: Cache action ('hit', 'miss', 'refresh', 'save')
        repo_name: Repository name for logging context
        **kwargs: Additional metrics (age_minutes, issue_count, reason, etc.)
    """
    if action == "hit":
        age_minutes = kwargs.get("age_minutes", 0)
        issue_count = kwargs.get("issue_count", 0)
        logger.debug(
            f"Cache hit for {repo_name}: age={age_minutes}m, issues={issue_count}"
        )
    elif action == "miss":
        reason = kwargs.get("reason", "unknown")
        logger.debug(f"Cache miss for {repo_name}: reason='{reason}'")
    elif action == "refresh":
        refresh_type = kwargs.get("refresh_type", "unknown")
        issue_count = kwargs.get("issue_count", 0)
        logger.debug(
            f"Cache refresh for {repo_name}: type={refresh_type}, new_issues={issue_count}"
        )
    elif action == "save":
        total_issues = kwargs.get("total_issues", 0)
        logger.debug(f"Cache save for {repo_name}: total_issues={total_issues}")


def _save_cache_file(cache_file_path: Path, cache_data: CacheData) -> bool:
    """Save cache data to file using atomic write.

    Each save writes to its own unique temp file in the target directory, so
    concurrent writers never share a temp path. The final ``os.replace`` is
    retried once after a short delay (Windows can briefly lock the target).
    The temp file is removed on every failure path.

    Args:
        cache_file_path: Path to cache file
        cache_data: CacheData to save

    Returns:
        True if successful, False otherwise
    """
    temp_path: Optional[str] = None
    try:
        # Ensure directory exists
        cache_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to unique temp file, then rename
        fd, temp_path = tempfile.mkstemp(
            dir=cache_file_path.parent,
            prefix=cache_file_path.name + ".",
            suffix=".tmp",
        )
        with os.fdopen(fd, "w") as f:
            json.dump(cache_data, f, indent=2)

        try:
            os.replace(temp_path, cache_file_path)  # Atomic rename
        except OSError:
            # Single retry; a second failure falls through to the outer handler
            time.sleep(_REPLACE_RETRY_DELAY_SECONDS)
            os.replace(temp_path, cache_file_path)
        return True

    except OSError as e:
        logger.warning(f"Cache save error for {cache_file_path}: {e}")
        return False

    finally:
        if temp_path is not None:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


def _get_cache_file_path(repo_identifier: RepoIdentifier) -> Path:
    """Get cache file path using RepoIdentifier.

    Args:
        repo_identifier: Repository identifier with owner and repo name

    Returns:
        Path to cache file
    """
    cache_dir = get_user_app_data_dir("mcp_coder") / "coordinator_cache"
    return cache_dir / f"{repo_identifier.cache_safe_name}.issues.json"
