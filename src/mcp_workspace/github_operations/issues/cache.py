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

from mcp_workspace.constants import DUPLICATE_PROTECTION_SECONDS
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


class CacheData(TypedDict):
    """Type definition for coordinator issue cache structure.

    Attributes:
        last_checked: ISO 8601 timestamp of last cache refresh, or None if never checked
        last_full_refresh: ISO 8601 timestamp of last successful full refresh, or None
        issues: Dictionary mapping issue number (as string) to IssueData
    """

    last_checked: Optional[str]
    last_full_refresh: NotRequired[Optional[str]]
    issues: Dict[str, IssueData]


def _load_cache_file(cache_file_path: Path) -> CacheData:
    """Load cache file or return empty cache structure.

    Args:
        cache_file_path: Path to cache file

    Returns:
        CacheData with last_checked and issues, or empty structure on errors
    """
    try:
        if not cache_file_path.exists():
            return {"last_checked": None, "last_full_refresh": None, "issues": {}}

        with cache_file_path.open("r") as f:
            data = json.load(f)

        # Validate structure
        if not isinstance(data, dict) or "issues" not in data:
            logger.warning(f"Invalid cache structure in {cache_file_path}, recreating")
            return {"last_checked": None, "last_full_refresh": None, "issues": {}}

        # Return as CacheData since we validated the structure
        return {
            "last_checked": data.get("last_checked"),
            "last_full_refresh": data.get("last_full_refresh"),
            "issues": data["issues"],
        }

    except (json.JSONDecodeError, OSError, PermissionError) as e:
        logger.warning(f"Cache load error for {cache_file_path}: {e}, starting fresh")
        return {"last_checked": None, "last_full_refresh": None, "issues": {}}


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

    Args:
        cache_file_path: Path to cache file
        cache_data: CacheData to save

    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure directory exists
        cache_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file, then rename
        temp_path = cache_file_path.with_suffix(".tmp")
        with temp_path.open("w") as f:
            json.dump(cache_data, f, indent=2)
        temp_path.replace(cache_file_path)  # Atomic rename

        return True

    except (OSError, PermissionError) as e:
        logger.warning(f"Cache save error for {cache_file_path}: {e}")
        return False


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


def _fetch_additional_issues(
    issue_manager: "IssueManager",
    additional_issue_numbers: list[int],
    repo_name: str,
    cache_data: CacheData,
) -> dict[str, IssueData]:
    """Fetch specific issues by number via individual API calls.

    Args:
        issue_manager: IssueManager for GitHub API calls
        additional_issue_numbers: List of issue numbers to fetch
        repo_name: Repository name for logging
        cache_data: Current cache data to check for existing issues

    Returns:
        Dict mapping issue number (as string) to IssueData.
        Includes issues already in cache (doesn't re-fetch but returns them).
    """
    result: dict[str, IssueData] = {}

    for issue_num in additional_issue_numbers:
        issue_key = str(issue_num)

        # Always re-fetch additional_issues to ensure fresh data
        try:
            issue = issue_manager.get_issue(issue_num)
            if issue["number"] != 0:  # Valid issue
                result[issue_key] = issue
                if issue_key in cache_data["issues"]:
                    logger.debug(
                        f"Refreshed issue #{issue_num} in cache for {repo_name}"
                    )
                else:
                    logger.debug(
                        f"Fetched additional issue #{issue_num} for {repo_name}"
                    )
        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
            if issue_key in cache_data["issues"]:
                result[issue_key] = cache_data["issues"][issue_key]
                logger.warning(
                    f"Failed to fetch issue #{issue_num}: {e}, using cached version"
                )
            else:
                logger.warning(f"Failed to fetch issue #{issue_num}: {e}")

    return result


def _fetch_and_merge_issues(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    issue_manager: "IssueManager",
    cache_data: CacheData,
    repo_name: str,
    force_refresh: bool,
    last_checked: Optional[datetime],
    now: datetime,
    cache_refresh_minutes: int,
    last_full_refresh: Optional[datetime] = None,
) -> Tuple[List[IssueData], bool]:
    """Fetch fresh issues and merge into cache.

    Args:
        issue_manager: IssueManager for GitHub API calls
        cache_data: Current cache data (will be modified)
        repo_name: Repository name for logging
        force_refresh: Whether to force full refresh
        last_checked: Last cache check timestamp (or None)
        now: Current UTC timestamp
        cache_refresh_minutes: Full refresh threshold in minutes
        last_full_refresh: Last full refresh timestamp (or None)

    Returns:
        Tuple of (fresh issues fetched from API, whether a full refresh was performed)
    """
    # Determine refresh strategy
    is_full_refresh = (
        force_refresh
        or not last_checked
        or not last_full_refresh
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

        # Clear cache on full refresh to remove closed issues
        cache_data["issues"] = {}
    else:
        # last_checked is guaranteed to be non-None here
        assert last_checked is not None
        cache_age_minutes = int((now - last_checked).total_seconds() / 60)
        logger.debug(
            f"Incremental refresh for {repo_name} since {last_checked} (age={cache_age_minutes}m)"
        )
        fresh_issues = issue_manager._list_issues_no_error_handling(
            state="all", include_pull_requests=False, since=last_checked
        )
        _log_cache_metrics(
            "refresh",
            repo_name,
            refresh_type="incremental",
            issue_count=len(fresh_issues),
        )

    return fresh_issues, is_full_refresh


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
                          Pass session issue numbers here to ensure closed session issues
                          are always fetched individually, regardless of refresh type or the
                          duplicate protection window (fetched before that check).

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

    # Step 2: Fetch additional issues BEFORE duplicate protection check
    additional_dict: dict[str, IssueData] = {}
    if additional_issues:
        logger.debug(
            f"Fetching {len(additional_issues)} additional issues for {repo_name}"
        )
        additional_dict = _fetch_additional_issues(
            issue_manager,
            additional_issues,
            repo_name,
            cache_data,
        )
        cache_data["issues"].update(additional_dict)
        if additional_dict:
            logger.debug(
                f"Added {len(additional_dict)} additional issues to cache for {repo_name}"
            )

    # Step 3: Check duplicate protection (50 second window)
    now = now_utc()
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

    # Save snapshot BEFORE fetch (in case full refresh clears cache_data["issues"])
    issues_snapshot = dict(cache_data["issues"])

    try:
        # Step 4: Fetch and merge issues
        fresh_issues, was_full_refresh = _fetch_and_merge_issues(
            issue_manager,
            cache_data,
            repo_name,
            force_refresh,
            last_checked,
            now,
            cache_refresh_minutes,
            last_full_refresh,
        )

        # Step 5: Update cache with fresh data
        fresh_dict = {str(issue["number"]): issue for issue in fresh_issues}
        cache_data["issues"].update(fresh_dict)

        # Step 5b: Restore additional issues (they may have been cleared during full refresh)
        if additional_dict:
            cache_data["issues"].update(additional_dict)

        cache_data["last_checked"] = format_for_cache(now)
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
