"""Label updates for the issue cache.

``update_issue_labels_in_cache`` swaps one label; ``set_issue_labels_in_cache``
replaces the whole set. Both write through ``_cache_io`` and never raise.
"""

import logging

from mcp_workspace.utils.repo_identifier import RepoIdentifier

from ._cache_io import _get_cache_file_path, _load_cache_file, _save_cache_file

logger = logging.getLogger(__name__)


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


def set_issue_labels_in_cache(
    repo_identifier: RepoIdentifier, issue_number: int, labels: list[str]
) -> None:
    """Replace a cached issue's whole label set. Never raises; debug-logs a miss.

    Only ``issues[key]["labels"]`` is touched. ``last_checked`` and
    ``cached_at`` are left alone: bumping ``last_checked`` would extend the
    duplicate protection window.

    Args:
        repo_identifier: Repository identifier with owner and repo name
        issue_number: GitHub issue number to update
        labels: Complete label set to store for the issue

    Note:
        An issue missing from the cache (e.g. a reference project the
        coordinator does not poll) is logged at debug level. Save failures
        and unexpected errors are logged as warnings.
    """
    try:
        cache_file_path = _get_cache_file_path(repo_identifier)
        cache_data = _load_cache_file(cache_file_path)

        issue = cache_data["issues"].get(str(issue_number))
        if issue is None:
            logger.debug(
                f"Issue #{issue_number} not in cache for {repo_identifier.full_name}, "
                "skipping label update"
            )
            return

        issue["labels"] = list(labels)

        if _save_cache_file(cache_file_path, cache_data):
            logger.debug(f"Set issue #{issue_number} labels in cache: {labels}")
        else:
            logger.warning(
                f"Cache update failed for issue #{issue_number}: save operation failed"
            )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(
            f"Unexpected error updating cache for issue #{issue_number}: {e}"
        )
