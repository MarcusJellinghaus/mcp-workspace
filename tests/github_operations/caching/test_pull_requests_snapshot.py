"""Tests for PullRequestCache layer 1: open-PR snapshot, base tips, save/merge."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import Mock, PropertyMock

import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.caching._store import cache_file_path
from mcp_workspace.github_operations.caching.errors import GitHubRateLimitError
from mcp_workspace.github_operations.caching.pull_requests import (
    PRS_CACHE_VERSION,
    OpenPullRequest,
    PullRequestCache,
    _fetch_open_prs,
    _parse_pr,
)
from mcp_workspace.github_operations.pr_manager import PullRequestManager
from mcp_workspace.utils.repo_identifier import RepoIdentifier
from mcp_workspace.utils.timezone_utils import format_for_cache, utc_now

_REPO = RepoIdentifier("o", "r")
_UPDATED = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)


def _mock_pr(
    number: int,
    branch: str,
    owner: str = "o",
    base: str = "main",
    sha: Optional[str] = None,
) -> Mock:
    pr = Mock()
    pr.number = number
    pr.head.ref = branch
    pr.head.sha = sha or f"sha{number}"
    pr.head.label = f"{owner}:{branch}"
    pr.base.ref = base
    pr.updated_at = _UPDATED
    pr.user.login = "alice"
    pr.author_association = "OWNER"
    pr.draft = False
    return pr


def _open_pr(number: int, branch: str, owner: str = "o") -> OpenPullRequest:
    return OpenPullRequest(
        number=number,
        head_branch=branch,
        head_sha=f"sha{number}",
        head_label=f"{owner}:{branch}",
        base_branch="main",
        updated_at=_UPDATED.isoformat(),
        user="alice",
        author_association="OWNER",
        draft=False,
    )


def _repo(prs: Optional[list[Mock]] = None) -> Mock:
    repo = Mock()
    repo.get_pulls.return_value = prs if prs is not None else []
    repo.get_branch.side_effect = lambda name: Mock(commit=Mock(sha=f"tip-{name}"))
    return repo


def _manager(repo: Optional[Mock]) -> Mock:
    manager = Mock(spec=PullRequestManager)
    manager.repo_identifier = _REPO
    manager._get_repository.return_value = repo
    return manager


def _rate_limit() -> GithubException:
    return GithubException(
        403, {"message": "API rate limit exceeded"}, {"X-RateLimit-Remaining": "0"}
    )


def _path() -> Any:
    return cache_file_path(_REPO, "prs")


def _read() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_path().read_text(encoding="utf-8"))
    assert data["version"] == PRS_CACHE_VERSION
    return data


def _write_raw(content: str) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _snapshot(
    age: timedelta = timedelta(seconds=10),
    prs: Optional[dict[str, OpenPullRequest]] = None,
    base_tips: Optional[dict[str, str]] = None,
    fetched_at: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "fetched_at": fetched_at or format_for_cache(utc_now() - age),
        "prs": prs if prs is not None else {"1": _open_pr(1, "1-a")},
        "base_tips": base_tips if base_tips is not None else {},
    }


def _slot(expires_in: timedelta = timedelta(hours=1)) -> dict[str, Any]:
    return {
        "fp": ["x"],
        "value": "clean",
        "expires_at": format_for_cache(utc_now() + expires_in),
    }


def _write(snapshot: dict[str, Any], results: Optional[dict[str, Any]] = None) -> None:
    _write_raw(
        json.dumps(
            {
                "version": PRS_CACHE_VERSION,
                "snapshot": snapshot,
                "results": results or {},
            }
        )
    )


class TestParser:
    """Tests for _parse_pr and _fetch_open_prs."""

    def test_parse_list_item(self) -> None:
        pr = _mock_pr(42, "42-x")
        for name in ("mergeable", "mergeable_state", "merged"):
            setattr(
                type(pr),
                name,
                PropertyMock(side_effect=AssertionError(f"{name} accessed")),
            )
        assert _parse_pr(pr) == _open_pr(42, "42-x")

    def test_parse_missing_optional_fields(self) -> None:
        pr = _mock_pr(1, "1-a")
        pr.updated_at = None
        pr.user = None
        pr.author_association = None
        parsed = _parse_pr(pr)
        assert parsed["updated_at"] is None
        assert parsed["user"] is None
        assert parsed["author_association"] == "NONE"

    def test_all_pages_iterated(self) -> None:
        repo = _repo([_mock_pr(n, f"{n}-b") for n in (1, 2, 3)])
        prs = _fetch_open_prs(repo)
        repo.get_pulls.assert_called_once_with(state="open")
        assert [p["number"] for p in prs] == [1, 2, 3]

    def test_fetch_error_propagates(self) -> None:
        repo = _repo()
        repo.get_pulls.side_effect = GithubException(500, {"message": "boom"}, {})
        with pytest.raises(GithubException):
            _fetch_open_prs(repo)


class TestFindPr:
    """Tests for PullRequestCache.find_pr."""

    def test_matches_own_branch(self) -> None:
        cache = PullRequestCache.load(_manager(_repo([_mock_pr(5, "5-x")])))
        found = cache.find_pr("5-x")
        assert found is not None
        assert found["number"] == 5

    def test_fork_pr_does_not_match(self) -> None:
        cache = PullRequestCache.load(
            _manager(_repo([_mock_pr(5, "5-x", owner="other")]))
        )
        assert cache.find_pr("5-x") is None

    def test_no_pr(self) -> None:
        cache = PullRequestCache.load(_manager(_repo([_mock_pr(5, "5-x")])))
        assert cache.find_pr("6-y") is None

    def test_list_fetched_once_per_run(self) -> None:
        repo = _repo([_mock_pr(5, "5-x")])
        cache = PullRequestCache.load(_manager(repo))
        cache.find_pr("5-x")
        cache.find_pr("6-y")
        repo.get_pulls.assert_called_once()

    def test_repository_unavailable_raises(self) -> None:
        cache = PullRequestCache.load(_manager(None))
        with pytest.raises(RuntimeError):
            cache.find_pr("5-x")


class TestDuplicateProtection:
    """Snapshot reuse within DUPLICATE_PROTECTION_SECONDS."""

    def test_recent_snapshot_reused(self) -> None:
        _write(_snapshot(timedelta(seconds=10), base_tips={"main": "m"}))
        repo = _repo()
        cache = PullRequestCache.load(_manager(repo))
        found = cache.find_pr("1-a")
        assert found is not None
        assert cache.base_tip("main") == "m"
        repo.get_pulls.assert_not_called()
        repo.get_branch.assert_not_called()

    def test_old_snapshot_refetched(self) -> None:
        _write(_snapshot(timedelta(seconds=120), base_tips={"main": "m"}))
        repo = _repo([_mock_pr(2, "2-b")])
        cache = PullRequestCache.load(_manager(repo))
        assert cache.find_pr("1-a") is None
        assert cache.base_tip("main") == "tip-main"
        repo.get_pulls.assert_called_once()
        repo.get_branch.assert_called_once_with("main")

    def test_reused_snapshot_not_rewritten(self) -> None:
        _write(_snapshot(timedelta(seconds=10)))
        before = _path().read_text(encoding="utf-8")
        cache = PullRequestCache.load(_manager(_repo()))
        cache.find_pr("1-a")
        cache.save()
        assert _path().read_text(encoding="utf-8") == before


class TestBaseTip:
    """Tests for PullRequestCache.base_tip."""

    def test_fetched_once_per_base(self) -> None:
        repo = _repo()
        cache = PullRequestCache.load(_manager(repo))
        assert cache.base_tip("main") == "tip-main"
        assert cache.base_tip("main") == "tip-main"
        repo.get_branch.assert_called_once_with("main")

    def test_new_base_in_window_saved_and_served(self) -> None:
        snapshot = _snapshot(timedelta(seconds=10), base_tips={"main": "m"})
        _write(snapshot)
        repo = _repo()
        cache = PullRequestCache.load(_manager(repo))
        assert cache.base_tip("develop") == "tip-develop"
        repo.get_pulls.assert_not_called()
        cache.save()

        saved = _read()["snapshot"]
        assert saved["fetched_at"] == snapshot["fetched_at"]
        assert saved["base_tips"] == {"main": "m", "develop": "tip-develop"}

        repo2 = _repo()
        assert PullRequestCache.load(_manager(repo2)).base_tip("develop") == (
            "tip-develop"
        )
        repo2.get_branch.assert_not_called()

    def test_equal_fetched_at_keeps_both_tips(self) -> None:
        _write(_snapshot(timedelta(seconds=10), base_tips={"main": "m"}))
        a = PullRequestCache.load(_manager(_repo()))
        b = PullRequestCache.load(_manager(_repo()))
        a.base_tip("develop")
        b.base_tip("release")
        a.save()
        b.save()
        assert _read()["snapshot"]["base_tips"] == {
            "main": "m",
            "develop": "tip-develop",
            "release": "tip-release",
        }

    def test_equal_fetched_at_does_not_overwrite_disk_tip(self) -> None:
        snapshot = _snapshot(timedelta(seconds=10))
        _write(snapshot)
        cache = PullRequestCache.load(_manager(_repo()))
        cache.base_tip("main")
        _write({**snapshot, "base_tips": {"main": "disk"}})
        cache.save()
        assert _read()["snapshot"]["base_tips"] == {"main": "disk"}


class TestErrors:
    """Fetch errors and rate limits."""

    def test_server_error_propagates_nothing_stored(self) -> None:
        _write(_snapshot(timedelta(seconds=120)))
        before = _path().read_text(encoding="utf-8")
        repo = _repo()
        repo.get_pulls.side_effect = GithubException(500, {"message": "boom"}, {})
        cache = PullRequestCache.load(_manager(repo))

        with pytest.raises(GithubException):
            cache.find_pr("1-a")
        cache.save()

        assert _path().read_text(encoding="utf-8") == before

    def test_error_not_treated_as_no_pr(self) -> None:
        repo = _repo([_mock_pr(5, "5-x")])
        repo.get_pulls.side_effect = [
            GithubException(500, {"message": "boom"}, {}),
            [_mock_pr(5, "5-x")],
        ]
        cache = PullRequestCache.load(_manager(repo))
        with pytest.raises(GithubException):
            cache.find_pr("5-x")
        assert cache.find_pr("5-x") is not None

    def test_list_rate_limit_raises_and_save_is_noop(self) -> None:
        repo = _repo()
        repo.get_pulls.side_effect = _rate_limit()
        cache = PullRequestCache.load(_manager(repo))

        with pytest.raises(GitHubRateLimitError):
            cache.find_pr("5-x")
        cache.save()

        assert not _path().exists()

    def test_base_tip_rate_limit_after_list_save_is_noop(self) -> None:
        repo = _repo([_mock_pr(5, "5-x")])
        repo.get_branch.side_effect = _rate_limit()
        cache = PullRequestCache.load(_manager(repo))
        cache.find_pr("5-x")

        with pytest.raises(GitHubRateLimitError):
            cache.base_tip("main")
        cache.save()

        assert not _path().exists()

    @pytest.mark.parametrize(
        "content",
        [
            "not json",
            json.dumps({"version": 99, "snapshot": _snapshot()}),
            json.dumps({"snapshot": _snapshot()}),
            json.dumps({"version": PRS_CACHE_VERSION, "snapshot": []}),
            json.dumps({"version": PRS_CACHE_VERSION, "snapshot": {"prs": {}}}),
            json.dumps(
                {
                    "version": PRS_CACHE_VERSION,
                    "snapshot": _snapshot(fetched_at="garbage"),
                }
            ),
            json.dumps(
                {
                    "version": PRS_CACHE_VERSION,
                    "snapshot": _snapshot(timedelta(seconds=120)),
                    "results": [],
                }
            ),
        ],
    )
    def test_corrupt_or_mismatched_file_rebuilds(self, content: str) -> None:
        _write_raw(content)
        repo = _repo([_mock_pr(5, "5-x")])
        cache = PullRequestCache.load(_manager(repo))
        assert cache.find_pr("5-x") is not None
        cache.save()
        assert set(_read()["snapshot"]["prs"]) == {"5"}


class TestSave:
    """Merge on save."""

    def test_fresh_snapshot_written(self) -> None:
        cache = PullRequestCache.load(_manager(_repo([_mock_pr(5, "5-x")])))
        cache.find_pr("5-x")
        cache.base_tip("main")
        cache.save()
        data = _read()
        assert data["snapshot"]["prs"] == {"5": _open_pr(5, "5-x")}
        assert data["snapshot"]["base_tips"] == {"main": "tip-main"}
        assert data["results"] == {}

    def test_save_without_fetch_writes_nothing(self) -> None:
        cache = PullRequestCache.load(_manager(_repo()))
        cache.save()
        assert not _path().exists()

    def test_newer_disk_snapshot_wins_and_prunes_results(self) -> None:
        repo = _repo([_mock_pr(1, "1-a"), _mock_pr(2, "2-b")])
        cache = PullRequestCache.load(_manager(repo))
        cache.find_pr("1-a")

        newer = _snapshot(
            fetched_at=format_for_cache(utc_now() + timedelta(seconds=5)),
            prs={"2": _open_pr(2, "2-b")},
        )
        _write(newer, {"1": {"ci": _slot()}, "2": {"ci": _slot()}})
        cache.save()

        data = _read()
        assert data["snapshot"] == newer
        assert set(data["results"]) == {"2"}

    def test_my_newer_snapshot_wins_and_prunes_closed_pr(self) -> None:
        _write(
            _snapshot(
                timedelta(seconds=120),
                prs={"1": _open_pr(1, "1-a"), "2": _open_pr(2, "2-b")},
            ),
            {"1": {"ci": _slot()}, "2": {"ci": _slot()}},
        )
        cache = PullRequestCache.load(_manager(_repo([_mock_pr(2, "2-b")])))
        cache.find_pr("2-b")
        cache.save()

        data = _read()
        assert set(data["snapshot"]["prs"]) == {"2"}
        assert set(data["results"]) == {"2"}

    def test_expired_disk_slots_dropped(self) -> None:
        _write(
            _snapshot(
                timedelta(seconds=120),
                prs={"1": _open_pr(1, "1-a"), "2": _open_pr(2, "2-b")},
            ),
            {
                "1": {"ci": _slot(-timedelta(seconds=1)), "feedback": _slot()},
                "2": {"ci": _slot(-timedelta(seconds=1))},
            },
        )
        repo = _repo([_mock_pr(1, "1-a"), _mock_pr(2, "2-b")])
        cache = PullRequestCache.load(_manager(repo))
        cache.find_pr("1-a")
        cache.save()

        assert set(_read()["results"]) == {"1"}
        assert set(_read()["results"]["1"]) == {"feedback"}
