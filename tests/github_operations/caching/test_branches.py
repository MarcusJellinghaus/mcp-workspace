"""Tests for BranchLookupCache and invalidate_branch_entry."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Callable, Optional
from unittest.mock import Mock, patch

import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.caching._store import (
    cache_file_path,
    is_expired,
    new_expiry,
)
from mcp_workspace.github_operations.caching.branches import (
    BRANCHES_CACHE_VERSION,
    BranchLookupCache,
    invalidate_branch_entry,
)
from mcp_workspace.github_operations.caching.errors import GitHubRateLimitError
from mcp_workspace.github_operations.issues import (
    BranchLookup,
    BranchLookupError,
    IssueBranchManager,
    IssueData,
)
from mcp_workspace.utils.repo_identifier import RepoIdentifier
from mcp_workspace.utils.timezone_utils import format_for_cache, utc_now

from .._issue_test_helpers import make_mock_issue

_REPO = RepoIdentifier("o", "r")
_OTHER_REPO = RepoIdentifier("o", "other")
_UPDATED = "2026-10-27T10:00:00Z"


def _issue(number: int, updated_at: Optional[str] = _UPDATED) -> IssueData:
    return IssueData(
        number=number,
        title="t",
        body="",
        state="open",
        labels=[],
        assignees=[],
        user=None,
        created_at=None,
        updated_at=updated_at,
        url="",
        locked=False,
        author_association=None,
    )


def _manager(
    result: Optional[BranchLookup] = None, repo: RepoIdentifier = _REPO
) -> Mock:
    manager = Mock(spec=IssueBranchManager)
    manager.repo_identifier = repo
    manager.resolve_branch_for_issue.return_value = result or BranchLookup(
        "found", "5-x"
    )
    return manager


def _rate_limit() -> GithubException:
    return GithubException(
        403, {"message": "API rate limit exceeded"}, {"X-RateLimit-Remaining": "0"}
    )


def _path(repo: RepoIdentifier = _REPO) -> Any:
    return cache_file_path(repo, "branches")


def _read_entries(repo: RepoIdentifier = _REPO) -> dict[str, Any]:
    data = json.loads(_path(repo).read_text(encoding="utf-8"))
    assert data["version"] == BRANCHES_CACHE_VERSION
    entries: dict[str, Any] = data["entries"]
    return entries


def _write_raw(content: str, repo: RepoIdentifier = _REPO) -> None:
    path = _path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entry(
    status: str = "found",
    branch: Optional[str] = "5-x",
    fp: Optional[list[Any]] = None,
    expires_in: timedelta = timedelta(hours=1),
) -> dict[str, Any]:
    return {
        "fp": fp if fp is not None else [_UPDATED],
        "status": status,
        "branch": branch,
        "expires_at": format_for_cache(utc_now() + expires_in),
    }


def _write_entries(entries: dict[str, Any], repo: RepoIdentifier = _REPO) -> None:
    _write_raw(
        json.dumps({"version": BRANCHES_CACHE_VERSION, "entries": entries}), repo
    )


class TestStoreExpiry:
    """Tests for the _store expiry helpers."""

    def test_new_expiry_within_jitter_window(self) -> None:
        now = utc_now()
        entry = {"expires_at": new_expiry(now)}
        assert not is_expired(entry, now + timedelta(hours=4, minutes=29))
        assert is_expired(entry, now + timedelta(hours=6, seconds=1))

    @pytest.mark.parametrize("value", [None, "garbage", 123])
    def test_missing_or_bad_expiry_is_expired(self, value: Any) -> None:
        entry = {} if value is None else {"expires_at": value}
        assert is_expired(entry, utc_now())


class TestLookup:
    """Tests for BranchLookupCache.lookup and save."""

    def test_miss_then_hit_across_loads(self) -> None:
        manager = _manager()
        cache = BranchLookupCache.load(manager)
        assert cache.lookup(_issue(5)) == BranchLookup("found", "5-x")
        manager.resolve_branch_for_issue.assert_called_once_with(5, "o", "r")
        cache.save()
        assert _read_entries()["5"]["fp"] == [_UPDATED]

        manager2 = _manager()
        cache2 = BranchLookupCache.load(manager2)
        assert cache2.lookup(_issue(5)) == BranchLookup("found", "5-x")
        manager2.resolve_branch_for_issue.assert_not_called()

    def test_hit_within_same_run(self) -> None:
        manager = _manager()
        cache = BranchLookupCache.load(manager)
        cache.lookup(_issue(5))
        cache.lookup(_issue(5))
        manager.resolve_branch_for_issue.assert_called_once()

    @pytest.mark.parametrize(
        "result",
        [
            BranchLookup("found", "5-x"),
            BranchLookup("not_found"),
            BranchLookup("ambiguous"),
        ],
    )
    def test_all_statuses_cached(self, result: BranchLookup) -> None:
        cache = BranchLookupCache.load(_manager(result))
        cache.lookup(_issue(5))
        cache.save()

        manager2 = _manager()
        assert BranchLookupCache.load(manager2).lookup(_issue(5)) == result
        manager2.resolve_branch_for_issue.assert_not_called()

    def test_changed_updated_at_re_resolves(self) -> None:
        _write_entries({"5": _entry()})
        manager = _manager(BranchLookup("not_found"))
        cache = BranchLookupCache.load(manager)
        result = cache.lookup(_issue(5, updated_at="2026-10-27T11:00:00Z"))
        assert result == BranchLookup("not_found")
        manager.resolve_branch_for_issue.assert_called_once()

    def test_expired_entry_re_resolves(self) -> None:
        _write_entries({"5": _entry(expires_in=-timedelta(seconds=1))})
        manager = _manager()
        BranchLookupCache.load(manager).lookup(_issue(5))
        manager.resolve_branch_for_issue.assert_called_once()

    @pytest.mark.parametrize(
        "exc",
        [
            BranchLookupError("incomplete"),
            GithubException(500, {"message": "Server Error"}, {}),
        ],
    )
    def test_resolver_error_propagates_nothing_stored(self, exc: Exception) -> None:
        _write_entries({"9": _entry()})
        before = _path().read_text(encoding="utf-8")
        manager = _manager()
        manager.resolve_branch_for_issue.side_effect = exc
        cache = BranchLookupCache.load(manager)

        with pytest.raises(type(exc)):
            cache.lookup(_issue(5))
        cache.save()

        assert _path().read_text(encoding="utf-8") == before

    def test_rate_limit_raises_and_save_is_noop(self) -> None:
        manager = _manager()
        cache = BranchLookupCache.load(manager)
        cache.lookup(_issue(4))
        manager.resolve_branch_for_issue.side_effect = _rate_limit()

        with pytest.raises(GitHubRateLimitError):
            cache.lookup(_issue(5))
        cache.save()

        assert not _path().exists()

    def test_graphql_rate_limited_linked_query_raises_and_save_is_noop(
        self,
    ) -> None:
        """A RATE_LIMITED linked-branches reply, as PyGithub raises it, stops the run."""
        with patch("mcp_workspace.github_operations._client.Github") as mock_github:
            manager = IssueBranchManager(
                repo_url="https://github.com/o/r", github_token="tok"
            )
            manager._cached_github_client = mock_github.return_value
        repo = Mock()
        repo.owner.login = "o"
        repo.name = "r"
        manager._repository = repo
        graphql_query = Mock(
            side_effect=[
                (
                    {},
                    {
                        "data": {
                            "repository": {
                                "issue": {
                                    "linkedBranches": {
                                        "nodes": [{"ref": {"name": "4-x"}}]
                                    }
                                }
                            }
                        }
                    },
                ),
                GithubException(
                    400,
                    {"data": None, "errors": [{"type": "RATE_LIMITED"}]},
                    {},
                ),
            ]
        )
        manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        manager._github_client._Github__requester.graphql_query = graphql_query  # type: ignore[attr-defined]
        cache = BranchLookupCache.load(manager)
        assert cache.lookup(_issue(4)) == BranchLookup("found", "4-x")

        with pytest.raises(GitHubRateLimitError):
            cache.lookup(_issue(5))
        cache.save()

        assert not _path().exists()

    # Builders, not strings: _entry() embeds utc_now(), and a timestamp in a
    # parameter value makes each xdist worker collect different test IDs.
    @pytest.mark.parametrize(
        "make_content",
        [
            lambda: "not json",
            lambda: json.dumps({"version": 99, "entries": {"5": _entry()}}),
            lambda: json.dumps({"entries": {"5": _entry()}}),
            lambda: json.dumps({"version": BRANCHES_CACHE_VERSION, "entries": []}),
            lambda: json.dumps(
                {"version": BRANCHES_CACHE_VERSION, "entries": {"5": "x"}}
            ),
        ],
        ids=[
            "not-json",
            "wrong-version",
            "no-version",
            "entries-list",
            "entry-not-dict",
        ],
    )
    def test_corrupt_or_mismatched_file_is_empty(
        self, make_content: Callable[[], str]
    ) -> None:
        _write_raw(make_content())
        manager = _manager()
        cache = BranchLookupCache.load(manager)
        assert cache.lookup(_issue(5)) == BranchLookup("found", "5-x")
        manager.resolve_branch_for_issue.assert_called_once()
        cache.save()
        assert set(_read_entries()) == {"5"}

    @pytest.mark.parametrize("missing", ["status", "branch"])
    def test_malformed_entry_is_miss(self, missing: str) -> None:
        entry = _entry()
        del entry[missing]  # fp still matches
        _write_entries({"5": entry})
        manager = _manager()
        cache = BranchLookupCache.load(manager)
        assert cache.lookup(_issue(5)) == BranchLookup("found", "5-x")
        manager.resolve_branch_for_issue.assert_called_once()

    def test_concurrent_writers_both_kept(self) -> None:
        a = BranchLookupCache.load(_manager(BranchLookup("found", "1-a")))
        b = BranchLookupCache.load(_manager(BranchLookup("found", "2-b")))
        a.lookup(_issue(1))
        b.lookup(_issue(2))
        a.save()
        b.save()
        entries = _read_entries()
        assert entries["1"]["branch"] == "1-a"
        assert entries["2"]["branch"] == "2-b"

    def test_expired_entry_dropped_at_save(self) -> None:
        _write_entries({"8": _entry(expires_in=-timedelta(seconds=1)), "9": _entry()})
        cache = BranchLookupCache.load(_manager())
        cache.lookup(_issue(5))
        cache.save()
        assert set(_read_entries()) == {"5", "9"}

    def test_save_without_fetch_writes_nothing(self) -> None:
        cache = BranchLookupCache.load(_manager())
        cache.save()
        assert not _path().exists()


class TestInvalidation:
    """Tests for invalidate_branch_entry."""

    def test_deleted_entry_not_resurrected(self) -> None:
        _write_entries({"5": _entry()})
        a = BranchLookupCache.load(_manager(BranchLookup("not_found")))

        invalidate_branch_entry(_REPO, 5)
        assert "5" not in _read_entries()

        a.lookup(_issue(6))
        a.save()
        entries = _read_entries()
        assert "5" not in entries
        assert "6" in entries

    def test_live_fetched_entry_dropped(self) -> None:
        a = BranchLookupCache.load(_manager(BranchLookup("not_found")))
        a.lookup(_issue(7))

        invalidate_branch_entry(_REPO, 7)
        a.save()

        assert not _path().exists() or "7" not in _read_entries()
        manager2 = _manager()
        BranchLookupCache.load(manager2).lookup(_issue(7))
        manager2.resolve_branch_for_issue.assert_called_once()

    def test_live_loaded_entry_dropped(self) -> None:
        _write_entries({"7": _entry(status="not_found", branch=None)})
        manager = _manager()
        a = BranchLookupCache.load(manager)

        invalidate_branch_entry(_REPO, 7)

        assert a.lookup(_issue(7)) == BranchLookup("found", "5-x")
        manager.resolve_branch_for_issue.assert_called_once()

    def test_other_repo_cache_untouched(self) -> None:
        other = BranchLookupCache.load(_manager(BranchLookup("not_found"), _OTHER_REPO))
        other.lookup(_issue(7))

        invalidate_branch_entry(_REPO, 7)
        other.save()

        assert "7" in _read_entries(_OTHER_REPO)

    def test_missing_file_is_noop(self) -> None:
        invalidate_branch_entry(_REPO, 5)
        assert not _path().exists()

    def test_never_raises(self) -> None:
        with patch(
            "mcp_workspace.github_operations.caching.branches._load_entries",
            side_effect=RuntimeError("boom"),
        ):
            invalidate_branch_entry(_REPO, 5)


class TestCreateBranchHook:
    """create_remote_branch_for_issue invalidates the entry only on success."""

    _TARGET = "mcp_workspace.github_operations.caching.branches.invalidate_branch_entry"

    @pytest.fixture
    def manager(self) -> IssueBranchManager:
        with patch("mcp_workspace.github_operations._client.Github") as mock_github:
            manager = IssueBranchManager(
                repo_url="https://github.com/o/r", github_token="tok"
            )
            manager._cached_github_client = mock_github.return_value
        repo = Mock()
        repo.node_id = "R_1"
        repo.default_branch = "main"
        repo.full_name = "o/r"
        issue = make_mock_issue(5, "o/r")
        issue.node_id = "I_5"
        issue.title = "Feature"
        repo.get_issue.return_value = issue
        repo.get_branch.return_value.commit.sha = "abc"
        manager._repository = repo
        manager.get_linked_branches = Mock(return_value=[])  # type: ignore[method-assign]
        manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
        return manager

    def _respond(self, manager: IssueBranchManager, response: dict[str, Any]) -> None:
        manager._github_client._Github__requester.graphql_named_mutation = Mock(  # type: ignore[attr-defined]
            return_value=({}, response)
        )

    def test_success_invalidates(self, manager: IssueBranchManager) -> None:
        self._respond(
            manager, {"linkedBranch": {"id": "LB", "ref": {"name": "5-feature"}}}
        )
        with patch(self._TARGET) as mock_invalidate:
            result = manager.create_remote_branch_for_issue(5)
        assert result["success"] is True
        mock_invalidate.assert_called_once_with(_REPO, 5)

    def test_failure_does_not_invalidate(self, manager: IssueBranchManager) -> None:
        self._respond(manager, {"errors": [{"message": "nope"}]})
        with patch(self._TARGET) as mock_invalidate:
            result = manager.create_remote_branch_for_issue(5)
        assert result["success"] is False
        mock_invalidate.assert_not_called()
