"""Disk cache for issue → branch resolution results.

One run-scoped object per repo: ``BranchLookupCache.load(manager)``, then
``lookup()`` per issue, then ``save()`` once. An entry is valid while the
issue's ``updated_at`` is unchanged and its ``expires_at`` is in the future.
"""

from __future__ import annotations

import logging
import weakref
from typing import TYPE_CHECKING, Any

from mcp_workspace.utils.repo_identifier import RepoIdentifier
from mcp_workspace.utils.timezone_utils import utc_now

from ..issues.types import BranchLookup, IssueData
from ._store import _save_cache_file, cache_file_path, is_expired, load_json, new_expiry
from .errors import GitHubRateLimitError, rate_limit_guard

if TYPE_CHECKING:
    # Type-only: issues.branch_manager imports this module at call time.
    from ..issues.branch_manager import IssueBranchManager

logger = logging.getLogger(__name__)

BRANCHES_CACHE_VERSION = 1

_SUFFIX = "branches"

# Live caches in this process, so invalidation also reaches in-memory entries.
_live: weakref.WeakSet[BranchLookupCache] = weakref.WeakSet()


def _load_entries(repo_identifier: RepoIdentifier) -> dict[str, dict[str, Any]]:
    """Load the valid-shaped entries of a repo's branches cache file. Never raises.

    Args:
        repo_identifier: Repository whose cache file is read.

    Returns:
        Entries keyed by issue number; empty if the file is missing or invalid.
    """
    path = cache_file_path(repo_identifier, _SUFFIX)
    entries = load_json(path, BRANCHES_CACHE_VERSION).get("entries", {})
    if not isinstance(entries, dict):
        return {}
    return {
        k: v
        for k, v in entries.items()
        if isinstance(v, dict) and "status" in v and "branch" in v
    }


def _write_entries(
    repo_identifier: RepoIdentifier, entries: dict[str, dict[str, Any]]
) -> None:
    """Write entries to a repo's branches cache file."""
    path = cache_file_path(repo_identifier, _SUFFIX)
    _save_cache_file(path, {"version": BRANCHES_CACHE_VERSION, "entries": entries})


class BranchLookupCache:
    """Run-scoped cache of ``resolve_branch_for_issue`` results for one repo."""

    def __init__(
        self, manager: IssueBranchManager, loaded: dict[str, dict[str, Any]]
    ) -> None:
        self._manager = manager
        self.repo_identifier = manager.repo_identifier
        self._loaded = loaded
        self._fetched: dict[str, dict[str, Any]] = {}
        self._rate_limited = False

    @classmethod
    def load(cls, manager: IssueBranchManager) -> BranchLookupCache:
        """Load the cache file for the manager's repository. Never raises on bad data.

        Args:
            manager: Branch manager of the repository to cache lookups for.

        Returns:
            A cache seeded with the valid entries from disk.
        """
        cache = cls(manager, _load_entries(manager.repo_identifier))
        _live.add(cache)
        return cache

    def lookup(self, issue: IssueData) -> BranchLookup:
        """Return the issue's branch, resolving it on a cache miss.

        Raises:
            GitHubRateLimitError: If resolution hit a rate limit; ``save()``
                then becomes a no-op.
        """  # noqa: DOC502  # other resolver errors propagate unchanged
        number = issue["number"]
        key = str(number)
        fp = [issue["updated_at"]]
        now = utc_now()

        entry = self._fetched.get(key) or self._loaded.get(key)
        if entry and entry.get("fp") == fp and not is_expired(entry, now):
            return BranchLookup(entry["status"], entry["branch"])

        ident = self.repo_identifier
        try:
            with rate_limit_guard():
                result = self._manager.resolve_branch_for_issue(
                    number, ident.owner, ident.repo_name
                )
        except GitHubRateLimitError:
            self._rate_limited = True
            raise

        self._fetched[key] = {
            "fp": fp,
            "status": result.status,
            "branch": result.branch,
            "expires_at": new_expiry(now),
        }
        return result

    def save(self) -> None:
        """Merge this run's fetched entries into the file on disk.

        No-op after a rate limit or when nothing was fetched.
        """
        if self._rate_limited or not self._fetched:
            return
        now = utc_now()
        entries = {
            k: v
            for k, v in _load_entries(self.repo_identifier).items()
            if not is_expired(v, now)
        }
        entries.update(self._fetched)
        _write_entries(self.repo_identifier, entries)

    def _forget(self, key: str) -> None:
        """Drop an entry from memory so it is neither served nor written back."""
        self._fetched.pop(key, None)
        self._loaded.pop(key, None)


def invalidate_branch_entry(repo_identifier: RepoIdentifier, issue_number: int) -> None:
    """Load the file, delete the issue's entry, save. Never raises."""
    key = str(issue_number)
    try:
        for cache in list(_live):
            if cache.repo_identifier == repo_identifier:
                cache._forget(key)  # pylint: disable=protected-access
        entries = _load_entries(repo_identifier)
        if entries.pop(key, None) is not None:
            _write_entries(repo_identifier, entries)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(
            f"Failed to invalidate branch cache entry for issue #{issue_number}: {e}"
        )
