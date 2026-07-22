"""Tests for issue cache functionality — schema fields, cursor, watermark, bookkeeping.

Split from the original test_issue_cache.py by whole test class. The module helper
``_make_cursor_issue`` is kept in this file together with its consumers.
"""

import json
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

import pytest
from mcp_coder_utils.user_app_data import get_user_app_data_dir

from mcp_workspace.constants import SINCE_OVERLAP_MINUTES
from mcp_workspace.github_operations.issues import (
    CacheData,
    IssueData,
    update_issue_labels_in_cache,
)
from mcp_workspace.github_operations.issues.cache import (
    CACHE_SCHEMA_VERSION,
    _get_cache_file_path,
    _load_cache_file,
    _log_cache_metrics,
    _log_stale_cache_entries,
    _save_cache_file,
    get_all_cached_issues,
)
from mcp_workspace.utils.repo_identifier import RepoIdentifier


class TestNewCacheSchemaFields:
    """Tests for the new schema fields surfaced by _load_cache_file.

    Covers updates_covered_through (data cursor), cached_at (sidecar map) and
    version (schema version), including backward compatibility with old-shape
    caches that lack these fields.
    """

    def test_load_cache_file_nonexistent_has_new_field_defaults(self) -> None:
        """Nonexistent cache returns safe defaults for all new schema fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "nonexistent.json"
            result = _load_cache_file(cache_path)

            assert result["updates_covered_through"] is None
            assert result["cached_at"] == {}
            assert result["version"] is None

    def test_load_cache_preserves_new_fields(self, tmp_path: Path) -> None:
        """A file containing all three new fields round-trips unchanged."""
        cache_file = tmp_path / "test.json"
        stored = {
            "last_checked": "2025-12-31T10:30:00Z",
            "last_full_refresh": "2025-12-31T10:30:00Z",
            "updates_covered_through": "2025-12-31T09:15:00Z",
            "cached_at": {"1": "2025-12-31T09:00:00Z"},
            "version": 1,
            "issues": {"1": {"number": 1, "state": "open", "labels": []}},
        }
        with cache_file.open("w") as f:
            json.dump(stored, f)

        loaded = _load_cache_file(cache_file)
        assert loaded["updates_covered_through"] == "2025-12-31T09:15:00Z"
        assert loaded["cached_at"] == {"1": "2025-12-31T09:00:00Z"}
        assert loaded["version"] == 1
        assert loaded["last_checked"] == "2025-12-31T10:30:00Z"
        assert "1" in loaded["issues"]

    def test_load_old_shape_cache_defaults_new_fields(self, tmp_path: Path) -> None:
        """Old-shape cache (only last_checked + issues) self-heal precondition.

        Loads with updates_covered_through/version None and cached_at {} while
        keeping issues intact - the None cursor is what triggers the self-healing
        full refresh in later steps.
        """
        cache_file = tmp_path / "test.json"
        old_cache = {
            "last_checked": "2025-12-31T10:30:00Z",
            "issues": {"1": {"number": 1, "state": "open", "labels": []}},
        }
        with cache_file.open("w") as f:
            json.dump(old_cache, f)

        loaded = _load_cache_file(cache_file)
        assert loaded["updates_covered_through"] is None
        assert loaded["version"] is None
        assert loaded["cached_at"] == {}
        assert "1" in loaded["issues"]


def _make_cursor_issue(number: int, updated_at: Optional[str]) -> IssueData:
    """Build a minimal IssueData with a given updated_at for cursor tests."""
    return {
        "number": number,
        "state": "open",
        "labels": [],
        "updated_at": updated_at,
        "url": f"https://github.com/test/repo/issues/{number}",
        "title": f"Issue {number}",
        "body": "",
        "assignees": [],
        "user": "testuser",
        "created_at": "2025-12-31T08:00:00Z",
        "locked": False,
    }


class TestUpdatesCoveredThrough:
    """Tests for the updates_covered_through data cursor in incremental refresh.

    Verifies the two-clock split: the cursor advances from the max observed
    ``updated_at`` over the incremental since-list only (never wall-clock now,
    never additional_issues), an empty list leaves it unchanged, and a missing
    or malformed cursor self-heals via a full refresh.
    """

    NOW = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)

    def _incremental_seed(
        self, updates_covered_through: Optional[str] = "2025-12-31T11:00:00+00:00"
    ) -> CacheData:
        """Cache seed that stays on the incremental path under ``NOW``.

        last_checked is 2 min old (outside duplicate protection), last_full_refresh
        is 2 h old (under the 24 h threshold), and updates_covered_through is set
        unless overridden with None (old-shape cache) or a malformed value.
        """
        seed: CacheData = {
            "last_checked": "2025-12-31T11:58:00+00:00",
            "last_full_refresh": "2025-12-31T10:00:00+00:00",
            "issues": {"1": _make_cursor_issue(1, "2025-12-31T09:00:00Z")},
        }
        if updates_covered_through is not None:
            seed["updates_covered_through"] = updates_covered_through
        return seed

    def _run(
        self,
        manager: Mock,
        cache_file: Path,
        seed: CacheData,
        *,
        force_refresh: bool = False,
        additional_issues: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Save the seed, run get_all_cached_issues, return the reloaded JSON."""
        _save_cache_file(cache_file, seed)
        get_all_cached_issues(
            RepoIdentifier.from_full_name("test/repo"),
            manager,
            force_refresh=force_refresh,
            additional_issues=additional_issues,
        )
        with cache_file.open("r") as f:
            data: Dict[str, Any] = json.load(f)
        return data

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_incremental_cursor_is_max_updated_at(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """Two incremental issues (A < B) -> saved cursor == max updated_at (B)."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = [
            _make_cursor_issue(10, "2025-12-31T11:30:00Z"),
            _make_cursor_issue(11, "2025-12-31T11:45:00Z"),
        ]

        saved = self._run(
            mock_cache_issue_manager, cache_file, self._incremental_seed()
        )

        assert saved["updates_covered_through"] == "2025-12-31T11:45:00+00:00"

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_full_refresh_cursor_is_now(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """A full refresh is a complete observation -> cursor == now."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = [
            _make_cursor_issue(10, "2025-12-31T09:00:00Z"),
        ]

        saved = self._run(
            mock_cache_issue_manager,
            cache_file,
            self._incremental_seed(),
            force_refresh=True,
        )

        assert saved["updates_covered_through"] == "2025-12-31T12:00:00+00:00"

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_empty_incremental_does_not_advance_cursor(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """An empty incremental list leaves the stored cursor unchanged."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = []

        saved = self._run(
            mock_cache_issue_manager, cache_file, self._incremental_seed()
        )

        assert saved["updates_covered_through"] == "2025-12-31T11:00:00+00:00"

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_none_updated_at_filtered(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """Issues with updated_at=None are filtered -> treated as empty."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = [
            _make_cursor_issue(10, None),
            _make_cursor_issue(11, None),
        ]

        saved = self._run(
            mock_cache_issue_manager, cache_file, self._incremental_seed()
        )

        assert saved["updates_covered_through"] == "2025-12-31T11:00:00+00:00"

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_additional_issues_excluded_from_cursor(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """A newer additional issue must not advance the cursor past the since-list."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        # Since-list max is 11:30; the additional issue is newer (11:59).
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = [
            _make_cursor_issue(10, "2025-12-31T11:30:00Z"),
        ]
        mock_cache_issue_manager.get_issue.return_value = _make_cursor_issue(
            99, "2025-12-31T11:59:00Z"
        )

        saved = self._run(
            mock_cache_issue_manager,
            cache_file,
            self._incremental_seed(),
            additional_issues=[99],
        )

        # Additional issue is cached but does not feed the cursor.
        assert "99" in saved["issues"]
        assert saved["updates_covered_through"] == "2025-12-31T11:30:00+00:00"

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_incremental_since_uses_cursor_minus_overlap(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """Incremental ``since`` floor == cursor - SINCE_OVERLAP_MINUTES."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = []

        self._run(mock_cache_issue_manager, cache_file, self._incremental_seed())

        cursor = datetime(2025, 12, 31, 11, 0, 0, tzinfo=timezone.utc)
        expected_since = cursor - timedelta(minutes=SINCE_OVERLAP_MINUTES)
        mock_cache_issue_manager._list_issues_no_error_handling.assert_called_once_with(
            state="all", include_pull_requests=False, since=expected_since
        )

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_old_shape_cache_triggers_full_refresh(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """Old-shape cache (no updates_covered_through) self-heals via full refresh."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = []

        self._run(
            mock_cache_issue_manager,
            cache_file,
            self._incremental_seed(updates_covered_through=None),
        )

        mock_cache_issue_manager._list_issues_no_error_handling.assert_called_once_with(
            state="open", include_pull_requests=False
        )

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_malformed_cursor_triggers_full_refresh(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """A malformed cursor parses to None and self-heals via full refresh."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = []

        self._run(
            mock_cache_issue_manager,
            cache_file,
            self._incremental_seed(updates_covered_through="not-a-timestamp"),
        )

        mock_cache_issue_manager._list_issues_no_error_handling.assert_called_once_with(
            state="open", include_pull_requests=False
        )

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_incremental_refresh_emits_debug_logs(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """DEBUG logs expose since, count, min/max updated_at and cursor before->after."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = [
            _make_cursor_issue(10, "2025-12-31T11:30:00Z"),
        ]

        with caplog.at_level(
            logging.DEBUG, logger="mcp_workspace.github_operations.issues.cache"
        ):
            self._run(mock_cache_issue_manager, cache_file, self._incremental_seed())

        assert "Incremental refresh for repo since" in caplog.text
        assert "Incremental result for repo" in caplog.text
        assert "count=1" in caplog.text
        assert "min=2025-12-31 11:30:00+00:00" in caplog.text
        assert "max=2025-12-31 11:30:00+00:00" in caplog.text
        # cursor before -> after
        assert "2025-12-31 11:00:00+00:00 -> 2025-12-31 11:30:00+00:00" in caplog.text


class TestWatermarkRecovery:
    """End-to-end recovery: a write missed at the since-boundary on one
    incremental refresh is re-queried and merged on the next, with no full refresh.
    """

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_missed_update_recovered_on_next_incremental(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """Two consecutive incremental refreshes recover a lag-hidden write."""
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file

        # Advance wall-clock between the two polls (>60s apart to clear
        # duplicate protection), both well under the 24 h full-refresh threshold.
        now1 = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
        now2 = datetime(2025, 12, 31, 12, 2, 0, tzinfo=timezone.utc)
        mock_now.side_effect = [now1, now2]

        # Cursor at 11:59; the missed write (11:57) sits inside the overlap
        # window [cursor - 5m, cursor] = [11:54, 11:59].
        seed: CacheData = {
            "last_checked": "2025-12-31T11:55:00+00:00",
            "last_full_refresh": "2025-12-31T10:00:00+00:00",
            "updates_covered_through": "2025-12-31T11:59:00+00:00",
            "issues": {"1": _make_cursor_issue(1, "2025-12-31T09:00:00Z")},
        }
        _save_cache_file(cache_file, seed)

        missed = _make_cursor_issue(42, "2025-12-31T11:57:00Z")
        # First poll: eventual-consistency lag hides the write.
        # Second poll: the overlap re-scan surfaces it.
        mock_cache_issue_manager._list_issues_no_error_handling.side_effect = [
            [],
            [missed],
        ]

        repo = RepoIdentifier.from_full_name("test/repo")
        get_all_cached_issues(repo, mock_cache_issue_manager)
        result = get_all_cached_issues(repo, mock_cache_issue_manager)

        # The missed issue is recovered on the second refresh.
        numbers = {issue["number"] for issue in result}
        assert 42 in numbers

        # Both refreshes were incremental (state="all"), never a full refresh.
        calls = mock_cache_issue_manager._list_issues_no_error_handling.call_args_list
        assert len(calls) == 2
        for call in calls:
            assert call.kwargs["state"] == "all"


class TestCacheBookkeeping:
    """Tests for the cached_at sidecar map and version stamping on save.

    Verifies the schema bookkeeping deliverables: ``version`` is written on every
    save, ``cached_at`` stamps every issue merged this refresh (fresh + additional)
    with the poll timestamp, and a full refresh rebuilds ``cached_at`` from scratch
    (dropping stale entries for issues no longer returned).
    """

    NOW = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
    NOW_STR = "2025-12-31T12:00:00+00:00"

    def _incremental_seed(self) -> CacheData:
        """Cache seed that stays on the incremental path under ``NOW``."""
        return {
            "last_checked": "2025-12-31T11:58:00+00:00",
            "last_full_refresh": "2025-12-31T10:00:00+00:00",
            "updates_covered_through": "2025-12-31T11:00:00+00:00",
            "issues": {"1": _make_cursor_issue(1, "2025-12-31T09:00:00Z")},
        }

    def _run(
        self,
        manager: Mock,
        cache_file: Path,
        seed: CacheData,
        *,
        force_refresh: bool = False,
        additional_issues: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Save the seed, run get_all_cached_issues, return the reloaded JSON."""
        _save_cache_file(cache_file, seed)
        get_all_cached_issues(
            RepoIdentifier.from_full_name("test/repo"),
            manager,
            force_refresh=force_refresh,
            additional_issues=additional_issues,
        )
        with cache_file.open("r") as f:
            data: Dict[str, Any] = json.load(f)
        return data

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_version_written_on_save(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """Every saved cache carries version == CACHE_SCHEMA_VERSION."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = [
            _make_cursor_issue(10, "2025-12-31T11:30:00Z"),
        ]

        saved = self._run(
            mock_cache_issue_manager, cache_file, self._incremental_seed()
        )

        assert saved["version"] == CACHE_SCHEMA_VERSION

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_cached_at_stamped_for_merged_issues(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """An incremental issue is stamped in cached_at with the poll timestamp."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = [
            _make_cursor_issue(10, "2025-12-31T11:30:00Z"),
        ]

        saved = self._run(
            mock_cache_issue_manager, cache_file, self._incremental_seed()
        )

        assert saved["cached_at"]["10"] == self.NOW_STR
        assert saved["cached_at"]["10"] == saved["last_checked"]

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_cached_at_rebuilt_on_full_refresh(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """A full refresh drops stale cached_at entries and stamps only fresh ones."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        # Seed a stale cached_at entry for an issue no longer returned.
        seed = self._incremental_seed()
        seed["cached_at"] = {"999": "2025-12-01T00:00:00+00:00"}
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = [
            _make_cursor_issue(10, "2025-12-31T09:00:00Z"),
        ]

        saved = self._run(
            mock_cache_issue_manager, cache_file, seed, force_refresh=True
        )

        assert "999" not in saved["cached_at"]
        assert set(saved["cached_at"].keys()) == {"10"}
        assert saved["cached_at"]["10"] == self.NOW_STR

    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_cached_at_includes_additional_issues(
        self,
        mock_now: Mock,
        mock_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """A force-fetched additional issue is stamped in cached_at."""
        mock_now.return_value = self.NOW
        cache_file = tmp_path / "test.json"
        mock_path.return_value = cache_file
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = [
            _make_cursor_issue(10, "2025-12-31T11:30:00Z"),
        ]
        mock_cache_issue_manager.get_issue.return_value = _make_cursor_issue(
            99, "2025-12-31T11:59:00Z"
        )

        saved = self._run(
            mock_cache_issue_manager,
            cache_file,
            self._incremental_seed(),
            additional_issues=[99],
        )

        assert saved["cached_at"]["99"] == self.NOW_STR
        assert saved["cached_at"]["10"] == self.NOW_STR
