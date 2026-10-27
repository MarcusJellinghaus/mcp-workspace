"""Issue cache module for GitHub operations.

This module provides caching functionality for GitHub issues to improve performance
and reduce API calls. It includes:
- CacheData TypedDict for cache structure
- Cache file operations (load, save, get path)
- Cache metrics logging
- Cache update operations for issue labels
- Main cache retrieval function get_all_cached_issues()
"""

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    NotRequired,
    Optional,
    Tuple,
    TypedDict,
)

from mcp_coder_utils.user_app_data import get_user_app_data_dir

from mcp_workspace.constants import DUPLICATE_PROTECTION_SECONDS, SINCE_OVERLAP_MINUTES
from mcp_workspace.utils.repo_identifier import RepoIdentifier
from mcp_workspace.utils.timezone_utils import (
    format_for_cache,
    is_within_duration,
    now_utc,
    parse_iso_timestamp,
)

from .types import IssueData

if TYPE_CHECKING:
    from .manager import IssueManager

logger = logging.getLogger(__name__)

# Cache-schema version written on every save. Not branched on: the self-healing
# migration keys off updates_covered_through absence (see _fetch_and_merge_issues).
CACHE_SCHEMA_VERSION: int = 1

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

        for attempt in range(2):
            try:
                os.replace(temp_path, cache_file_path)  # Atomic rename
                return True
            except OSError:
                if attempt == 1:
                    raise
                time.sleep(_REPLACE_RETRY_DELAY_SECONDS)
        return False  # pragma: no cover - loop always returns or raises

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


def update_issue_labels_in_cache(
    repo_identifier: RepoIdentifier, issue_number: int, old_label: str, new_label: str
) -> None:
    """Update issue labels in cache after successful dispatch.

    Updates the cached issue labels to reflect GitHub label changes made
    during workflow dispatch. This prevents stale cache data from causing
    duplicate dispatches within the 1-minute duplicate protection window.

    Args:
        repo_identifier: Repository identifier with owner and repo name
        issue_number: GitHub issue number to update
        old_label: Label to remove from cached issue
        new_label: Label to add to cached issue

    Note:
        Cache update failures are logged as warnings but do not interrupt
        the main workflow. The next cache refresh will fetch correct data
        from GitHub API.
    """
    try:
        # Step 1: Load existing cache
        cache_file_path = _get_cache_file_path(repo_identifier)
        cache_data = _load_cache_file(cache_file_path)

        # Step 2: Find target issue in cache
        issue_key = str(issue_number)
        if issue_key not in cache_data["issues"]:
            logger.warning(
                f"Issue #{issue_number} not found in cache for {repo_identifier.full_name}"
            )
            return

        # Step 3: Update issue labels
        issue = cache_data["issues"][issue_key]
        current_labels = list(issue.get("labels", []))

        # Remove old label if present
        if old_label in current_labels:
            current_labels.remove(old_label)

        # Add new label if not already present
        if new_label and new_label not in current_labels:
            current_labels.append(new_label)

        # Update cached issue
        issue["labels"] = current_labels
        cache_data["issues"][issue_key] = issue

        # Step 4: Save updated cache
        save_success = _save_cache_file(cache_file_path, cache_data)
        if save_success:
            logger.debug(
                f"Updated issue #{issue_number} labels in cache: '{old_label}' -> '{new_label}'"
            )
        else:
            logger.warning(
                f"Cache update failed for issue #{issue_number}: save operation failed"
            )

    except Exception as e:  # pylint: disable=broad-exception-caught
        # Any unexpected errors - don't break main workflow
        logger.warning(
            f"Unexpected error updating cache for issue #{issue_number}: {e}"
        )


def _log_stale_cache_entries(
    cached_issues: Dict[str, IssueData], fresh_issues: Dict[str, IssueData]
) -> None:
    """Log detailed staleness information when cached data differs from fresh data.

    Args:
        cached_issues: Issues from cache (issue_number -> IssueData)
        fresh_issues: Fresh issues from API (issue_number -> IssueData)
    """
    # Check for state/label changes in existing issues
    for issue_num, cached_issue in cached_issues.items():
        if issue_num in fresh_issues:
            fresh_issue = fresh_issues[issue_num]

            # Check state changes
            if cached_issue.get("state") != fresh_issue.get("state"):
                logger.info(
                    f"Issue #{issue_num}: cached state '{cached_issue.get('state')}' != "
                    f"actual '{fresh_issue.get('state')}'"
                )

            # Check label changes
            cached_labels = set(cached_issue.get("labels", []))
            fresh_labels = set(fresh_issue.get("labels", []))
            if cached_labels != fresh_labels:
                logger.info(
                    f"Issue #{issue_num}: cached labels {sorted(cached_labels)} != "
                    f"actual {sorted(fresh_labels)}"
                )
        else:
            # Issue not in fresh_issues (could be closed, not truly deleted)
            if cached_issue.get("state") == "open":
                logger.info(f"Issue #{issue_num}: no longer exists in repository")


def _needs_fetch(
    cache_data: CacheData,
    key: str,
    now: datetime,
    cache_refresh_minutes: int,
    force_refresh: bool,
) -> bool:
    """Decide whether an additional issue must be fetched individually.

    Args:
        cache_data: Current cache data
        key: Issue number as string
        now: Current UTC timestamp
        cache_refresh_minutes: Maximum age of a cached entry in minutes
        force_refresh: A forced refresh bypasses the cache

    Returns:
        True when ``force_refresh`` is set, the issue is not cached, or its
        ``cached_at`` stamp is missing, unparseable or older than
        ``cache_refresh_minutes``.
    """
    if force_refresh or key not in cache_data["issues"]:
        return True
    cached_at_str = cache_data.get("cached_at", {}).get(key)
    if not cached_at_str:
        return True
    try:
        cached_at = parse_iso_timestamp(cached_at_str)
    except ValueError:
        return True
    return (now - cached_at) > timedelta(minutes=cache_refresh_minutes)


def _fetch_additional_issues(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    issue_manager: "IssueManager",
    additional_issue_numbers: list[int],
    repo_name: str,
    cache_data: CacheData,
    now: datetime,
    cache_refresh_minutes: int,
    force_refresh: bool,
) -> set[str]:
    """Fetch specific issues by number via individual API calls, when needed.

    An issue is fetched only when ``_needs_fetch`` says so (forced refresh, not
    cached, or ``cached_at`` missing/unparseable/stale). Fetched issues are
    written into ``cache_data["issues"]`` and stamped in ``cache_data["cached_at"]``
    with ``now``, in place. A failed fetch keeps any cached copy and its old stamp.

    Args:
        issue_manager: IssueManager for GitHub API calls
        additional_issue_numbers: List of issue numbers to fetch
        repo_name: Repository name for logging
        cache_data: Current cache data (modified in place)
        now: Current UTC timestamp
        cache_refresh_minutes: Maximum age of a cached entry in minutes
        force_refresh: Fetch every issue regardless of cache state

    Returns:
        Set of issue keys (issue number as string) actually fetched and written.
    """
    fetched: set[str] = set()
    now_str = format_for_cache(now)
    cached_at = cache_data.setdefault("cached_at", {})

    for issue_num in additional_issue_numbers:
        issue_key = str(issue_num)
        if not _needs_fetch(
            cache_data, issue_key, now, cache_refresh_minutes, force_refresh
        ):
            continue

        try:
            issue = issue_manager.get_issue(issue_num)
        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
            if issue_key in cache_data["issues"]:
                logger.warning(
                    f"Failed to fetch issue #{issue_num}: {e}, using cached version"
                )
            else:
                logger.warning(f"Failed to fetch issue #{issue_num}: {e}")
            continue

        if issue["number"] != 0:  # Valid issue
            if issue_key in cache_data["issues"]:
                logger.debug(f"Refreshed issue #{issue_num} in cache for {repo_name}")
            else:
                logger.debug(f"Fetched additional issue #{issue_num} for {repo_name}")
            cache_data["issues"][issue_key] = issue
            cached_at[issue_key] = now_str
            fetched.add(issue_key)

    return fetched


def _fetch_and_merge_issues(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    issue_manager: "IssueManager",
    cache_data: CacheData,
    repo_name: str,
    force_refresh: bool,
    last_checked: Optional[datetime],
    now: datetime,
    cache_refresh_minutes: int,
    last_full_refresh: Optional[datetime] = None,
    updates_covered_through: Optional[datetime] = None,
) -> Tuple[List[IssueData], bool, Optional[datetime]]:
    """Fetch fresh issues and merge into cache.

    Splits the wall-clock poll time (``last_checked``) from the data cursor
    (``updates_covered_through``). Incremental refreshes use the cursor minus a
    fixed ``SINCE_OVERLAP_MINUTES`` margin as the ``since`` floor, and the
    returned ``new_cursor`` is the honest high-water mark (max ``updated_at``
    actually observed in the incremental list), never wall-clock ``now``.

    Args:
        issue_manager: IssueManager for GitHub API calls
        cache_data: Current cache data (will be modified)
        repo_name: Repository name for logging
        force_refresh: Whether to force full refresh
        last_checked: Last cache check timestamp (or None)
        now: Current UTC timestamp
        cache_refresh_minutes: Full refresh threshold in minutes
        last_full_refresh: Last full refresh timestamp (or None)
        updates_covered_through: Parsed data cursor (max observed ``updated_at``)
            used as the ``since`` floor, or None for old-shape caches (which
            triggers a self-healing full refresh).

    Returns:
        Tuple of (fresh issues fetched from API, whether a full refresh was
        performed, new data cursor). ``new_cursor`` is ``now`` on full refresh,
        the max ``updated_at`` over the incremental list on incremental refresh,
        or None when the incremental list is empty (so the caller leaves the
        stored cursor unchanged).
    """
    # Determine refresh strategy. A missing updates_covered_through (old-shape
    # cache) self-heals via one full refresh.
    is_full_refresh = (
        force_refresh
        or not last_checked
        or not last_full_refresh
        or not updates_covered_through
        or (now - last_full_refresh) > timedelta(minutes=cache_refresh_minutes)
    )

    # Fetch issues using appropriate method
    if is_full_refresh:
        refresh_type = "force" if force_refresh else "full"
        logger.debug(f"Full refresh for {repo_name} (type={refresh_type})")
        fresh_issues = issue_manager._list_issues_no_error_handling(
            state="open", include_pull_requests=False
        )
        _log_cache_metrics(
            "refresh",
            repo_name,
            refresh_type=refresh_type,
            issue_count=len(fresh_issues),
        )

        # Log staleness if we had cached data
        if cache_data["issues"]:
            fresh_dict = {str(issue["number"]): issue for issue in fresh_issues}
            _log_stale_cache_entries(cache_data["issues"], fresh_dict)

        # Clear cache on full refresh to remove closed issues. Rebuild the
        # cached_at sidecar from scratch too, dropping stale entries for issues
        # no longer returned (re-stamped from fresh_dict in get_all_cached_issues).
        cache_data["issues"] = {}
        cache_data["cached_at"] = {}

        # A full, unfiltered enumeration is a complete observation.
        new_cursor: Optional[datetime] = now
    else:
        # last_checked / updates_covered_through are guaranteed non-None here
        assert last_checked is not None
        assert updates_covered_through is not None

        # Re-scan a short trailing window to absorb GitHub's since-index lag.
        since = updates_covered_through - timedelta(minutes=SINCE_OVERLAP_MINUTES)
        cache_age_minutes = int((now - last_checked).total_seconds() / 60)
        logger.debug(
            f"Incremental refresh for {repo_name} since {since} "
            f"(cursor={updates_covered_through}, overlap={SINCE_OVERLAP_MINUTES}m, "
            f"last_checked_age={cache_age_minutes}m)"
        )
        fresh_issues = issue_manager._list_issues_no_error_handling(
            state="all", include_pull_requests=False, since=since
        )
        _log_cache_metrics(
            "refresh",
            repo_name,
            refresh_type="incremental",
            issue_count=len(fresh_issues),
        )

        # Advance the cursor from the max updated_at actually observed, not
        # wall-clock now. None values are filtered; an empty list leaves the
        # cursor unchanged (an empty response is exactly the lag hiding a write).
        stamps = [
            parse_iso_timestamp(updated)
            for issue in fresh_issues
            if (updated := issue.get("updated_at"))
        ]
        new_cursor = max(stamps) if stamps else None
        min_stamp = min(stamps) if stamps else None
        max_stamp = max(stamps) if stamps else None
        gap = new_cursor - updates_covered_through if new_cursor is not None else None
        logger.debug(
            f"Incremental result for {repo_name}: count={len(fresh_issues)}, "
            f"updated_at min={min_stamp} max={max_stamp}, "
            f"cursor {updates_covered_through} -> {new_cursor} (gap={gap}), "
            f"numbers={[issue['number'] for issue in fresh_issues]}"
        )

    return fresh_issues, is_full_refresh, new_cursor


def get_all_cached_issues(  # pylint: disable=too-many-locals
    repo_identifier: RepoIdentifier,
    issue_manager: "IssueManager",
    force_refresh: bool = False,
    cache_refresh_minutes: int = 1440,
    additional_issues: list[int] | None = None,
) -> List[IssueData]:
    """Get all cached issues using cache for performance and duplicate protection.

    This function handles:
    - Cache loading and saving
    - Duplicate protection (skip if checked < 50 seconds ago)
    - Refresh strategy (full vs incremental based on age)
    - Fetching fresh issues from GitHub API
    - Merging fresh issues into cache

    Args:
        repo_identifier: RepoIdentifier for the repository
        issue_manager: IssueManager for GitHub API calls
        force_refresh: Bypass cache entirely
        cache_refresh_minutes: Full refresh threshold (default: 1440 = 24 hours)
        additional_issues: Extends the full refresh with known closed issues.
                          Full refresh uses state="open" so closed issues are never returned.
                          Pass session issue numbers here; each is fetched individually
                          (before the duplicate protection check) only when not cached,
                          its cached_at is missing/stale, or force_refresh is set. Cached
                          copies are put back after a full refresh clears the cache.

    Returns:
        List of ALL cached issues (unfiltered). Caller is responsible for filtering.
        Returns empty list if duplicate protection triggers.

    Note:
        Caller (thin wrapper) should handle fallback to direct API fetch.
    """
    # Step 1: Load cache
    cache_data = _load_cache_file(_get_cache_file_path(repo_identifier))
    repo_name = repo_identifier.repo_name

    # Log cache metrics
    _log_cache_metrics(
        "miss" if not cache_data["last_checked"] else "hit",
        repo_name,
        reason="no_cache" if not cache_data["last_checked"] else "cache_found",
    )

    # Parse last_checked timestamp
    last_checked = None
    if cache_data["last_checked"]:
        try:
            last_checked = parse_iso_timestamp(cache_data["last_checked"])
        except ValueError as e:
            logger.debug(
                f"Invalid timestamp in cache: {cache_data['last_checked']}, error: {e}"
            )

    # Parse last_full_refresh timestamp
    last_full_refresh = None
    last_full_refresh_str = cache_data.get("last_full_refresh")
    if last_full_refresh_str:
        try:
            last_full_refresh = parse_iso_timestamp(last_full_refresh_str)
        except ValueError as e:
            logger.debug(
                f"Invalid last_full_refresh in cache: {last_full_refresh_str}, error: {e}"
            )

    # Parse updates_covered_through data cursor (like last_full_refresh). A
    # missing or malformed value stays None and self-heals via a full refresh.
    updates_covered_through = None
    updates_covered_through_str = cache_data.get("updates_covered_through")
    if updates_covered_through_str:
        try:
            updates_covered_through = parse_iso_timestamp(updates_covered_through_str)
        except ValueError as e:
            logger.debug(
                f"Invalid updates_covered_through in cache: "
                f"{updates_covered_through_str}, error: {e}"
            )

    now = now_utc()

    # Step 2: Fetch additional issues BEFORE duplicate protection check
    fetched_keys: set[str] = set()
    if additional_issues:
        logger.debug(
            f"Checking {len(additional_issues)} additional issues for {repo_name}"
        )
        fetched_keys = _fetch_additional_issues(
            issue_manager,
            additional_issues,
            repo_name,
            cache_data,
            now,
            cache_refresh_minutes,
            force_refresh,
        )
        if fetched_keys:
            logger.debug(
                f"Fetched {len(fetched_keys)} additional issues into cache for {repo_name}"
            )

    # Step 3: Check duplicate protection (50 second window)
    if (
        not force_refresh
        and last_checked
        and is_within_duration(last_checked, DUPLICATE_PROTECTION_SECONDS, now)
    ):
        age_seconds = int((now - last_checked).total_seconds())
        _log_cache_metrics(
            "hit",
            repo_name,
            age_minutes=0,
            reason=f"duplicate_protection_{age_seconds}s",
        )
        logger.debug(f"Skipping {repo_name} - checked {age_seconds}s ago")
        return list(cache_data["issues"].values())

    # Save snapshots BEFORE fetch (in case full refresh clears cache_data["issues"]
    # and cached_at). Taken after step 2, so fetched keys carry the new stamp.
    issues_snapshot = dict(cache_data["issues"])
    cached_at_snapshot = dict(cache_data.get("cached_at", {}))

    try:
        # Step 4: Fetch and merge issues
        fresh_issues, was_full_refresh, new_cursor = _fetch_and_merge_issues(
            issue_manager,
            cache_data,
            repo_name,
            force_refresh,
            last_checked,
            now,
            cache_refresh_minutes,
            last_full_refresh,
            updates_covered_through,
        )

        # Step 5: Update cache with fresh data
        fresh_dict = {str(issue["number"]): issue for issue in fresh_issues}
        cache_data["issues"].update(fresh_dict)

        # Step 5b: Put back additional issues the full refresh cleared (closed
        # session issues are never in the state=open list), with their cached_at
        # stamp. Issues in fresh_dict keep the fresh version.
        # Note: additional issues are fetched by number, bypassing `since`, so
        # they must never feed the data cursor (new_cursor already excludes them).
        cached_at = cache_data.setdefault("cached_at", {})
        for issue_num in additional_issues or []:
            issue_key = str(issue_num)
            if issue_key in fresh_dict or issue_key not in issues_snapshot:
                continue
            cache_data["issues"][issue_key] = issues_snapshot[issue_key]
            if issue_key in cached_at_snapshot:
                cached_at[issue_key] = cached_at_snapshot[issue_key]

        # Step 5c: Stamp the cached_at sidecar for every issue in fresh_dict. On
        # full refresh cached_at was reset to {} in _fetch_and_merge_issues, so
        # this (with step 5b) rebuilds it from scratch.
        now_str = format_for_cache(now)
        for issue_key in fresh_dict:
            cached_at[issue_key] = now_str
        cache_data["version"] = CACHE_SCHEMA_VERSION

        cache_data["last_checked"] = format_for_cache(now)
        if new_cursor is not None:
            cache_data["updates_covered_through"] = format_for_cache(new_cursor)
        if was_full_refresh:
            cache_data["last_full_refresh"] = format_for_cache(now)

        # Step 6: Save cache
        if _save_cache_file(_get_cache_file_path(repo_identifier), cache_data):
            _log_cache_metrics(
                "save", repo_name, total_issues=len(cache_data["issues"])
            )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("API fetch failed for %s, returning stale cache", repo_name)
        cache_data["issues"] = issues_snapshot
        cache_data["cached_at"] = cached_at_snapshot
        return list(cache_data["issues"].values())

    # Step 7: Return ALL cached issues (unfiltered)
    all_cached_issues = list(cache_data["issues"].values())
    _log_cache_metrics(
        "hit",
        repo_name,
        age_minutes=(
            int((now - last_checked).total_seconds() / 60) if last_checked else 0
        ),
        issue_count=len(all_cached_issues),
    )
    logger.debug(f"Cache returned {len(all_cached_issues)} issues for {repo_name}")
    return all_cached_issues
