"""Disk cache for open pull requests and their fingerprinted results.

One run-scoped object per repo: ``PullRequestCache.load(pr_manager)``, then
query methods, then ``save()`` once. Layer 1 is a snapshot of the open-PR
list plus base-branch tip SHAs; within ``DUPLICATE_PROTECTION_SECONDS`` of
its ``fetched_at`` neither is re-fetched. On save the newer snapshot wins
whole, and results for PRs not in it are pruned.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, TypedDict, TypeVar

from github.PullRequest import PullRequest
from github.Repository import Repository

from mcp_workspace.constants import DUPLICATE_PROTECTION_SECONDS
from mcp_workspace.utils.timezone_utils import (
    format_for_cache,
    is_within_duration,
    parse_iso_timestamp,
    utc_now,
)

from ..trust import normalize_author_association
from ._store import _save_cache_file, cache_file_path, is_expired, load_json
from .errors import GitHubRateLimitError, rate_limit_guard

if TYPE_CHECKING:
    from ..pr_manager import PullRequestManager

logger = logging.getLogger(__name__)

PRS_CACHE_VERSION = 1

_SUFFIX = "prs"

_T = TypeVar("_T")


class OpenPullRequest(TypedDict):
    """One open PR from the list endpoint (no lazy-loaded fields)."""

    number: int
    head_branch: str
    head_sha: str
    head_label: str  # "<owner>:<branch>"
    base_branch: str
    updated_at: str | None
    user: str | None
    author_association: str
    draft: bool


def _parse_pr(pr: PullRequest) -> OpenPullRequest:
    """Parse a pull-request-simple list item field by field.

    Never touches ``mergeable*`` / ``merged``, which would lazy-load the PR.
    """
    return OpenPullRequest(
        number=pr.number,
        head_branch=pr.head.ref,
        head_sha=pr.head.sha,
        head_label=pr.head.label,
        base_branch=pr.base.ref,
        updated_at=pr.updated_at.isoformat() if pr.updated_at else None,
        user=pr.user.login if pr.user else None,
        author_association=normalize_author_association(pr.author_association)
        or "NONE",
        draft=bool(pr.draft),
    )


def _fetch_open_prs(repo: Repository) -> list[OpenPullRequest]:
    """Fetch every page of open PRs. Undecorated: all errors propagate."""
    return [_parse_pr(pr) for pr in repo.get_pulls(state="open")]


def _valid_snapshot(value: Any) -> dict[str, Any] | None:
    """Return the snapshot if it is well-shaped, else None."""
    if not isinstance(value, dict):
        return None
    fetched_at = value.get("fetched_at")
    prs = value.get("prs")
    base_tips = value.get("base_tips")
    if not (
        isinstance(fetched_at, str)
        and isinstance(prs, dict)
        and isinstance(base_tips, dict)
    ):
        return None
    try:
        parse_iso_timestamp(fetched_at)
    except ValueError:
        return None
    return {
        "fetched_at": fetched_at,
        "prs": {k: v for k, v in prs.items() if isinstance(v, dict)},
        "base_tips": {k: v for k, v in base_tips.items() if isinstance(v, str)},
    }


def _valid_results(value: Any) -> dict[str, dict[str, Any]]:
    """Return the per-PR result slots that are well-shaped."""
    if not isinstance(value, dict):
        return {}
    return {
        key: {s: e for s, e in slots.items() if isinstance(e, dict)}
        for key, slots in value.items()
        if isinstance(slots, dict)
    }


class PullRequestCache:
    """Run-scoped cache of open PRs and per-PR results for one repo."""

    def __init__(self, pr_manager: PullRequestManager, data: dict[str, Any]) -> None:
        self._pr_manager = pr_manager
        self.repo_identifier = pr_manager.repo_identifier
        self._path = cache_file_path(self.repo_identifier, _SUFFIX)
        self._loaded_snapshot = _valid_snapshot(data.get("snapshot"))
        self._loaded_results = _valid_results(data.get("results", {}))
        self._fetched_results: dict[str, dict[str, Any]] = {}
        self._snapshot: dict[str, Any] | None = None
        self._snapshot_dirty = False
        self._rate_limited = False
        self._repo: Repository | None = None

    @classmethod
    def load(cls, pr_manager: PullRequestManager) -> PullRequestCache:
        """Load the cache file for the manager's repository. Never raises on bad data."""
        path = cache_file_path(pr_manager.repo_identifier, _SUFFIX)
        return cls(pr_manager, load_json(path, PRS_CACHE_VERSION))

    def find_pr(self, branch: str) -> OpenPullRequest | None:
        """Return the open PR whose head is ``<owner>:<branch>``, else None.

        Raises:
            GitHubRateLimitError: If fetching hit a rate limit; ``save()``
                then becomes a no-op.
        """  # noqa: DOC502  # other fetch errors propagate unchanged
        return self._guarded(self._find_pr, branch)

    def base_tip(self, base_branch: str) -> str:
        """Return the tip SHA of a base branch, fetched once per snapshot.

        Raises:
            GitHubRateLimitError: If fetching hit a rate limit; ``save()``
                then becomes a no-op.
        """  # noqa: DOC502  # other fetch errors propagate unchanged
        return self._guarded(self._base_tip, base_branch)

    def save(self) -> None:
        """Merge this run's snapshot and fetched results into the file on disk.

        No-op after a rate limit or when nothing was fetched.
        """
        if self._rate_limited or not (self._snapshot_dirty or self._fetched_results):
            return
        now = utc_now()
        disk = load_json(self._path, PRS_CACHE_VERSION)
        snapshot = self._merged_snapshot(_valid_snapshot(disk.get("snapshot")))
        if snapshot is None:
            return

        results: dict[str, dict[str, Any]] = {}
        for key, slots in _valid_results(disk.get("results", {})).items():
            kept = {s: e for s, e in slots.items() if not is_expired(e, now)}
            if kept:
                results[key] = kept
        for key, slots in self._fetched_results.items():
            results.setdefault(key, {}).update(slots)
        results = {k: v for k, v in results.items() if k in snapshot["prs"]}

        _save_cache_file(
            self._path,
            {"version": PRS_CACHE_VERSION, "snapshot": snapshot, "results": results},
        )

    def _guarded(self, fn: Callable[..., _T], *args: Any) -> _T:
        """Call fn under rate_limit_guard; a rate limit disables ``save()``."""
        try:
            with rate_limit_guard():
                return fn(*args)
        except GitHubRateLimitError:
            self._rate_limited = True
            raise

    def _repository(self) -> Repository:
        """Return the manager's repository, raising if it is unavailable."""
        if self._repo is None:
            repo = (
                self._pr_manager._get_repository()
            )  # pylint: disable=protected-access
            if repo is None:
                raise RuntimeError(
                    f"Repository {self.repo_identifier.full_name} not accessible"
                )
            self._repo = repo
        return self._repo

    def _snapshot_or_fetch(self) -> dict[str, Any]:
        """Return this run's snapshot, reusing a recent loaded one or fetching."""
        if self._snapshot is not None:
            return self._snapshot
        now = utc_now()
        loaded = self._loaded_snapshot
        if loaded and is_within_duration(
            parse_iso_timestamp(loaded["fetched_at"]),
            DUPLICATE_PROTECTION_SECONDS,
            now,
        ):
            self._snapshot = loaded
        else:
            prs = _fetch_open_prs(self._repository())
            self._snapshot = {
                "fetched_at": format_for_cache(now),
                "prs": {str(pr["number"]): pr for pr in prs},
                "base_tips": {},
            }
            self._snapshot_dirty = True
        return self._snapshot

    def _find_pr(self, branch: str) -> OpenPullRequest | None:
        label = f"{self.repo_identifier.owner}:{branch}"
        for pr in self._snapshot_or_fetch()["prs"].values():
            if pr.get("head_label") == label:
                found: OpenPullRequest = pr
                return found
        return None

    def _base_tip(self, base_branch: str) -> str:
        base_tips: dict[str, str] = self._snapshot_or_fetch()["base_tips"]
        if base_branch not in base_tips:
            base_tips[base_branch] = (
                self._repository().get_branch(base_branch).commit.sha
            )
            self._snapshot_dirty = True
        return base_tips[base_branch]

    def _merged_snapshot(self, disk: dict[str, Any] | None) -> dict[str, Any] | None:
        """Pick the newer of disk and my snapshot; on a tie, add my missing tips."""
        mine = self._snapshot
        if mine is None or disk is None:
            return mine or disk
        disk_at = parse_iso_timestamp(disk["fetched_at"])
        mine_at = parse_iso_timestamp(mine["fetched_at"])
        if disk_at > mine_at:
            return disk
        if mine_at > disk_at:
            return mine
        tips = {**mine["base_tips"], **disk["base_tips"]}
        return {**disk, "base_tips": tips}
