"""Tests for the label disk cache (get_cached_labels)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from github.GithubException import GithubException
from requests.exceptions import RetryError

from mcp_workspace.github_operations.caching._store import cache_file_path
from mcp_workspace.github_operations.caching.errors import GitHubRateLimitError
from mcp_workspace.github_operations.caching.labels import (
    LABELS_CACHE_VERSION,
    CachedLabels,
    get_cached_labels,
)
from mcp_workspace.github_operations.labels_manager import LabelData
from mcp_workspace.utils.repo_identifier import RepoIdentifier
from mcp_workspace.utils.timezone_utils import format_for_cache, utc_now

_REPO = RepoIdentifier("owner", "repo")
_GHE_REPO = RepoIdentifier("owner", "repo", hostname="ghe.corp.com")
_RESET_EPOCH = 1_900_000_000

_OLD: list[LabelData] = [
    {"name": "old", "color": "000000", "description": "", "url": "u-old"}
]
_NEW: list[LabelData] = [
    {"name": "bug", "color": "d73a4a", "description": "Broken", "url": "u-bug"},
    {"name": "status-01:created", "color": "ffffff", "description": "", "url": "u-s"},
]
_OLD_FETCHED_AT = "2026-01-01T00:00:00+00:00"


def _manager(repo: RepoIdentifier = _REPO) -> MagicMock:
    manager = MagicMock()
    manager.repo_identifier = repo
    manager.get_available_labels.return_value = _NEW
    return manager


def _path(repo: RepoIdentifier = _REPO) -> Path:
    return cache_file_path(repo, "labels")


def _write(data: Any, repo: RepoIdentifier = _REPO, raw: str | None = None) -> Path:
    path = _path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw if raw is not None else json.dumps(data), encoding="utf-8")
    return path


def _entry(
    expired: bool = False, labels: Any = None, version: int = LABELS_CACHE_VERSION
) -> dict[str, Any]:
    offset = timedelta(hours=-1) if expired else timedelta(hours=1)
    return {
        "version": version,
        "fetched_at": _OLD_FETCHED_AT,
        "expires_at": format_for_cache(utc_now() + offset),
        "labels": _OLD if labels is None else labels,
    }


def _rate_limit() -> GithubException:
    return GithubException(
        403,
        {"message": "API rate limit exceeded"},
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(_RESET_EPOCH)},
    )


def _read(repo: RepoIdentifier = _REPO) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_path(repo).read_text(encoding="utf-8"))
    return data


def _plain_footer(fetched_at: str) -> str:
    return f"Label cache last updated {fetched_at}"


class TestFreshFetch:
    """A miss fetches and writes the file."""

    def test_miss_fetches_and_writes(self) -> None:
        manager = _manager()
        result = get_cached_labels(manager)

        manager.get_available_labels.assert_called_once_with()
        assert _path().name == "github_com_owner_repo.labels.json"
        data = _read()
        assert data["version"] == LABELS_CACHE_VERSION
        assert data["labels"] == _NEW
        assert isinstance(data["fetched_at"], str)
        assert isinstance(data["expires_at"], str)
        assert result == CachedLabels(_NEW, _plain_footer(data["fetched_at"]))

    def test_valid_entry_no_fetch(self) -> None:
        _write(_entry())
        manager = _manager()
        result = get_cached_labels(manager)

        manager.get_available_labels.assert_not_called()
        assert result == CachedLabels(_OLD, _plain_footer(_OLD_FETCHED_AT))

    def test_expired_entry_refetches(self) -> None:
        _write(_entry(expired=True))
        manager = _manager()
        result = get_cached_labels(manager)

        manager.get_available_labels.assert_called_once_with()
        assert result.labels == _NEW
        assert _read()["labels"] == _NEW

    def test_refresh_refetches_valid_entry(self) -> None:
        _write(_entry())
        manager = _manager()
        result = get_cached_labels(manager, refresh=True)

        manager.get_available_labels.assert_called_once_with()
        assert result.labels == _NEW
        assert _read()["labels"] == _NEW

    def test_fresh_expiry_within_24h(self) -> None:
        before = utc_now()
        get_cached_labels(_manager())
        expires = datetime.fromisoformat(_read()["expires_at"])
        assert before + timedelta(hours=18) <= expires
        assert expires <= utc_now() + timedelta(hours=24)


class TestRateLimit:
    """A rate-limited reload falls back to an existing entry."""

    def test_expired_entry_falls_back(self) -> None:
        path = _write(_entry(expired=True))
        before = path.read_text(encoding="utf-8")
        manager = _manager()
        manager.get_available_labels.side_effect = _rate_limit()

        result = get_cached_labels(manager)

        reset = format_for_cache(datetime.fromtimestamp(_RESET_EPOCH, tz=UTC))
        assert result.labels == _OLD
        assert result.footer == (
            f"Label cache last updated {_OLD_FETCHED_AT}"
            f" — refresh failed: rate limited until {reset}"
        )
        assert path.read_text(encoding="utf-8") == before

    def test_refresh_on_valid_entry_falls_back(self) -> None:
        path = _write(_entry())
        before = path.read_text(encoding="utf-8")
        manager = _manager()
        manager.get_available_labels.side_effect = _rate_limit()

        result = get_cached_labels(manager, refresh=True)

        assert result.labels == _OLD
        assert "rate limited until" in result.footer
        assert path.read_text(encoding="utf-8") == before

    def test_unknown_reset_time(self) -> None:
        _write(_entry(expired=True))
        manager = _manager()
        manager.get_available_labels.side_effect = RetryError()

        result = get_cached_labels(manager)

        assert result.labels == _OLD
        assert result.footer == (
            f"Label cache last updated {_OLD_FETCHED_AT}"
            " — refresh failed: rate limited (reset time unknown)"
        )

    def test_no_entry_raises(self) -> None:
        manager = _manager()
        manager.get_available_labels.side_effect = _rate_limit()

        with pytest.raises(GitHubRateLimitError):
            get_cached_labels(manager)
        assert not _path().exists()


def test_other_error_propagates_and_file_unchanged() -> None:
    path = _write(_entry(expired=True))
    before = path.read_text(encoding="utf-8")
    manager = _manager()
    manager.get_available_labels.side_effect = GithubException(
        500, {"message": "boom"}, {}
    )

    with pytest.raises(GithubException):
        get_cached_labels(manager)
    assert path.read_text(encoding="utf-8") == before


class TestInvalidEntry:
    """Invalid files and entries count as a miss."""

    def test_corrupt_file(self) -> None:
        _write(None, raw="not json")
        manager = _manager()
        assert get_cached_labels(manager).labels == _NEW
        manager.get_available_labels.assert_called_once_with()

    def test_version_mismatch(self) -> None:
        _write(_entry(version=LABELS_CACHE_VERSION + 1))
        manager = _manager()
        assert get_cached_labels(manager).labels == _NEW
        manager.get_available_labels.assert_called_once_with()

    @pytest.mark.parametrize(
        "labels",
        [
            [{"name": "x", "color": "c", "url": "u"}],
            [{"name": "x", "color": "c", "description": None, "url": "u"}],
            [{"name": 1, "color": "c", "description": "", "url": "u"}],
            ["x"],
            {"name": "x"},
        ],
        ids=["missing-description", "none-description", "int-name", "str", "dict"],
    )
    def test_malformed_labels_refetch_and_rewrite(self, labels: Any) -> None:
        _write(_entry(labels=labels))
        manager = _manager()

        assert get_cached_labels(manager).labels == _NEW
        manager.get_available_labels.assert_called_once_with()
        assert _read()["labels"] == _NEW

    @pytest.mark.parametrize("fetched_at", [None, 123, "not-a-date"])
    def test_malformed_fetched_at(self, fetched_at: Any) -> None:
        entry = _entry()
        entry["fetched_at"] = fetched_at
        _write(entry)
        manager = _manager()

        assert get_cached_labels(manager).labels == _NEW
        manager.get_available_labels.assert_called_once_with()


def test_github_com_and_ghe_use_different_files() -> None:
    assert _path(_REPO) != _path(_GHE_REPO)
    _write(_entry())

    manager = _manager(_GHE_REPO)
    assert get_cached_labels(manager).labels == _NEW
    manager.get_available_labels.assert_called_once_with()
    assert _read(_GHE_REPO)["labels"] == _NEW
    assert _read(_REPO)["labels"] == _OLD
