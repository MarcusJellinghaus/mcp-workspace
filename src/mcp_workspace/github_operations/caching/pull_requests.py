"""Disk cache for open pull requests and their fingerprinted results.

One run-scoped object per repo: ``PullRequestCache.load(pr_manager)``, then
query methods, then ``save()`` once. Layer 1 is a snapshot of the open-PR
list plus base-branch tip SHAs; within ``DUPLICATE_PROTECTION_SECONDS`` of
its ``fetched_at`` neither is re-fetched. On save the newer snapshot wins
whole, and results for PRs not in it are pruned.

Layer 2 keeps four result slots per PR (``mergeable_state``, ``ci``,
``feedback``, ``label_events``). Each entry stores a fingerprint ``fp`` that
starts with the issue's ``updated_at``; a hit needs a matching ``fp`` and an
unexpired entry. Not-final results are returned but never stored, and fetch
errors propagate without storing anything.
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

from ..ci_results_manager import CIStatusData, RunData, aggregate_conclusion
from ..issues.events_mixin import EventsMixin
from ..issues.types import EventData, IssueData, IssueEventType
from ..pr_types import PRFeedback
from ..trust import normalize_author_association
from ._store import (
    _save_cache_file,
    cache_file_path,
    is_expired,
    load_json,
    new_expiry,
)
from .errors import (
    GitHubRateLimitError,
    graphql_rate_limit_error,
    rate_limit_guard,
    to_rate_limit_error,
)

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


def _fetch_ci_status(
    repo: Repository, head_sha: str, branch: str
) -> tuple[CIStatusData, bool]:
    """Fetch the aggregate CI status of a commit, without jobs.

    Undecorated: all errors propagate.

    Returns:
        ``(status, final)`` — ``final`` is True only if there are runs and
        every run is ``completed``. ``aggregate_conclusion`` already reports
        ``("failure", "completed")`` while other runs are still going, so its
        status cannot decide finality.
    """
    runs: list[Any] = list(repo.get_workflow_runs(head_sha=head_sha)[:25])
    if not runs:
        return CIStatusData(run={}, jobs=[]), False  # type: ignore[typeddict-item]
    conclusion, status = aggregate_conclusion(runs)
    first = runs[0]
    run_data: RunData = {
        "run_ids": [r.id for r in runs],
        "status": status,
        "conclusion": conclusion,
        "workflow_name": first.name,
        "event": first.event,
        "workflow_path": first.path,
        "branch": branch,
        "commit_sha": head_sha,
        "created_at": first.created_at.isoformat() if first.created_at else "",
        "url": first.html_url,
    }
    final = all(r.status == "completed" for r in runs)
    return CIStatusData(run=run_data, jobs=[]), final


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

    def mergeable_state(self, pr: OpenPullRequest, issue: IssueData) -> str | None:
        """Return the PR's ``mergeable_state``; stored unless ``unknown`` / None.

        Raises:
            GitHubRateLimitError: If fetching hit a rate limit; ``save()``
                then becomes a no-op.
        """  # noqa: DOC502  # other fetch errors propagate unchanged
        return self._guarded(self._mergeable_state, pr, issue)

    def ci_status(self, pr: OpenPullRequest, issue: IssueData) -> CIStatusData:
        """Return the aggregate CI status of the PR head; stored once all runs completed.

        Raises:
            GitHubRateLimitError: If fetching hit a rate limit; ``save()``
                then becomes a no-op.
        """  # noqa: DOC502  # other fetch errors propagate unchanged
        return self._guarded(self._ci_status, pr, issue)

    def feedback(self, pr: OpenPullRequest, issue: IssueData) -> PRFeedback:
        """Return PR feedback without alerts; stored unless a section is unavailable.

        Raises:
            GitHubRateLimitError: If fetching (or any feedback section) hit a
                rate limit; ``save()`` then becomes a no-op.
        """  # noqa: DOC502  # other fetch errors propagate unchanged
        return self._guarded(self._feedback, pr, issue)

    def label_events(self, pr: OpenPullRequest, issue: IssueData) -> list[EventData]:
        """Return the issue's ``labeled`` events; always stored.

        Raises:
            GitHubRateLimitError: If fetching hit a rate limit; ``save()``
                then becomes a no-op.
        """  # noqa: DOC502  # other fetch errors propagate unchanged
        return self._guarded(self._label_events, pr, issue)

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

    def _cached(
        self, pr: OpenPullRequest, slot: str, fp: list[Any]
    ) -> tuple[bool, Any]:
        """Return ``(True, value)`` for an unexpired entry with matching fp."""
        key = str(pr["number"])
        now = utc_now()
        for results in (self._fetched_results, self._loaded_results):
            entry = results.get(key, {}).get(slot)
            if (
                entry is not None
                and entry.get("fp") == fp
                and not is_expired(entry, now)
            ):
                return True, entry.get("value")
        return False, None

    def _store(self, pr: OpenPullRequest, slot: str, fp: list[Any], value: Any) -> None:
        """Record a final result for this run's ``save()``."""
        self._fetched_results.setdefault(str(pr["number"]), {})[slot] = {
            "fp": fp,
            "value": value,
            "expires_at": new_expiry(utc_now()),
        }

    def _mergeable_state(self, pr: OpenPullRequest, issue: IssueData) -> str | None:
        fp = [issue["updated_at"], pr["head_sha"], self._base_tip(pr["base_branch"])]
        hit, value = self._cached(pr, "mergeable_state", fp)
        if hit:
            cached: str | None = value
            return cached
        state = self._repository().get_pull(pr["number"]).mergeable_state
        if state not in (None, "unknown"):
            self._store(pr, "mergeable_state", fp, state)
        return state

    def _ci_status(self, pr: OpenPullRequest, issue: IssueData) -> CIStatusData:
        fp = [issue["updated_at"], pr["head_sha"]]
        hit, value = self._cached(pr, "ci", fp)
        if hit:
            cached: CIStatusData = value
            return cached
        status, final = _fetch_ci_status(
            self._repository(), pr["head_sha"], pr["head_branch"]
        )
        if final:
            self._store(pr, "ci", fp, status)
        return status

    def _feedback(self, pr: OpenPullRequest, issue: IssueData) -> PRFeedback:
        fp = [issue["updated_at"], pr["updated_at"]]
        hit, value = self._cached(pr, "feedback", fp)
        if hit:
            cached: PRFeedback = value
            return cached
        # Undecorated body: the decorator's empty default on an unexpected
        # error would look like "no feedback" and be cached.
        feedback = (
            self._pr_manager._collect_pr_feedback(  # pylint: disable=protected-access
                pr["number"], include_alerts=False
            )
        )
        for exc in feedback["unavailable"].values():
            # A GraphQL RATE_LIMITED body arrives as a status-400 exception
            # without rate-limit headers, so check its data as well.
            rl = to_rate_limit_error(exc) or graphql_rate_limit_error(
                getattr(exc, "data", None)
            )
            if rl is not None:
                raise rl from exc
        if feedback["unavailable"]:
            return feedback
        self._store(pr, "feedback", fp, {**feedback, "unavailable": {}, "skipped": {}})
        return feedback

    def _label_events(self, pr: OpenPullRequest, issue: IssueData) -> list[EventData]:
        fp = [issue["updated_at"]]
        hit, value = self._cached(pr, "label_events", fp)
        if hit:
            cached: list[EventData] = value
            return cached
        # Unbound call with the PullRequestManager: get_issue_events only needs
        # BaseGitHubManager's _get_repository / _get_issue_checked, so no
        # second (IssueManager) instance is needed.
        events = EventsMixin.get_issue_events(
            self._pr_manager, issue["number"], IssueEventType.LABELED
        )
        self._store(pr, "label_events", fp, events)
        return events

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
