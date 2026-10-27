"""Tests for the generic JSON cache store and get_issue_cache_last_checked."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from mcp_workspace.github_operations.caching._store import (
    _save_cache_file,
    cache_file_path,
    load_json,
)
from mcp_workspace.github_operations.issues import get_issue_cache_last_checked
from mcp_workspace.utils.repo_identifier import RepoIdentifier

_REPO = RepoIdentifier("o", "r")


class TestCacheFilePath:
    """Tests for cache_file_path."""

    def test_path_layout(self, cache_dir: Path) -> None:
        path = cache_file_path(_REPO, "prs")
        assert path == (
            cache_dir / "coordinator_cache" / f"{_REPO.cache_safe_name}.prs.json"
        )

    def test_issues_suffix_matches_issue_cache(self) -> None:
        from mcp_workspace.github_operations.issues import (  # pylint: disable=import-outside-toplevel
            _get_cache_file_path,
        )

        assert _get_cache_file_path(_REPO) == cache_file_path(_REPO, "issues")


class TestLoadJson:
    """Tests for load_json."""

    def test_missing_file(self, tmp_path: Path) -> None:
        assert load_json(tmp_path / "missing.json") == {}

    def test_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        assert load_json(path) == {}

    def test_non_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "list.json"
        path.write_text("[1, 2]", encoding="utf-8")
        assert load_json(path) == {}

    @pytest.mark.parametrize("data", [{"version": 2, "a": 1}, {"a": 1}])
    def test_version_mismatch_or_missing(
        self, tmp_path: Path, data: dict[str, Any]
    ) -> None:
        path = tmp_path / "v.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        assert load_json(path, expected_version=1) == {}

    def test_matching_version(self, tmp_path: Path) -> None:
        path = tmp_path / "v.json"
        data = {"version": 1, "a": 1}
        path.write_text(json.dumps(data), encoding="utf-8")
        assert load_json(path, expected_version=1) == data

    def test_no_expected_version(self, tmp_path: Path) -> None:
        path = tmp_path / "v.json"
        data = {"version": 7, "a": 1}
        path.write_text(json.dumps(data), encoding="utf-8")
        assert load_json(path) == data


def test_save_round_trips_through_load_json(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "x.prs.json"
    data = {"version": 1, "entries": {"1": {"fp": ["a"]}}}
    assert _save_cache_file(path, data) is True
    assert load_json(path, expected_version=1) == data


class TestGetIssueCacheLastChecked:
    """Tests for get_issue_cache_last_checked."""

    def _write(self, content: str) -> None:
        path = cache_file_path(_REPO, "issues")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_returns_aware_datetime(self) -> None:
        self._write(
            json.dumps({"last_checked": "2026-01-02T03:04:05+00:00", "issues": {}})
        )
        result = get_issue_cache_last_checked(_REPO)
        assert result == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        assert result is not None and result.tzinfo is not None

    def test_z_suffix_parsed(self) -> None:
        self._write(json.dumps({"last_checked": "2026-01-02T03:04:05Z", "issues": {}}))
        assert get_issue_cache_last_checked(_REPO) == datetime(
            2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc
        )

    def test_missing_file(self) -> None:
        assert get_issue_cache_last_checked(_REPO) is None

    def test_missing_key(self) -> None:
        self._write(json.dumps({"issues": {}}))
        assert get_issue_cache_last_checked(_REPO) is None

    @pytest.mark.parametrize(
        "content",
        [
            "garbage",
            json.dumps({"last_checked": "not-a-date", "issues": {}}),
            json.dumps({"last_checked": 12345, "issues": {}}),
        ],
    )
    def test_garbage(self, content: str) -> None:
        self._write(content)
        assert get_issue_cache_last_checked(_REPO) is None


def test_underscore_exports_still_importable() -> None:
    from mcp_workspace.github_operations.issues import (
        _get_cache_file_path,
        _load_cache_file,
        _log_stale_cache_entries,
    )
    from mcp_workspace.github_operations.issues import (
        _save_cache_file as reexported,
    )  # pylint: disable=import-outside-toplevel,unused-import

    assert reexported is _save_cache_file
