"""Tests for issue cache functionality — last_full_refresh field.

Split from the original test_issue_cache.py by whole test class.
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
from mcp_workspace.github_operations import IssueIdentityMismatchError
from mcp_workspace.github_operations.issues import (
    CacheData,
    IssueData,
    update_issue_labels_in_cache,
)
from mcp_workspace.github_operations.issues._cache_io import (
    _get_cache_file_path,
    _load_cache_file,
    _log_cache_metrics,
    _save_cache_file,
)
from mcp_workspace.github_operations.issues.cache import (
    CACHE_SCHEMA_VERSION,
    _log_stale_cache_entries,
    get_all_cached_issues,
)
from mcp_workspace.utils.repo_identifier import RepoIdentifier


class TestLastFullRefresh:
    """Tests for the last_full_refresh field in CacheData."""

    def test_last_full_refresh_in_cache_data(self, tmp_path: Path) -> None:
        """Test that last_full_refresh field persists through save/load cycle."""
        cache_file = tmp_path / "test.json"
        cache_data: CacheData = {
            "last_checked": "2025-12-31T10:30:00Z",
            "last_full_refresh": "2025-12-31T09:00:00Z",
            "issues": {},
        }
        _save_cache_file(cache_file, cache_data)

        loaded = _load_cache_file(cache_file)
        assert loaded["last_full_refresh"] == "2025-12-31T09:00:00Z"
        assert loaded["last_checked"] == "2025-12-31T10:30:00Z"

    @patch(
        "mcp_workspace.github_operations.issues.cache._get_cache_file_path",
    )
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_full_refresh_updates_last_full_refresh(
        self,
        mock_now: Mock,
        mock_cache_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """Test that a full refresh updates last_full_refresh in saved cache."""
        now = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = now

        cache_file = tmp_path / "test.json"
        mock_cache_path.return_value = cache_file

        # Start with empty cache (no last_checked) → triggers full refresh
        cache_data: CacheData = {
            "last_checked": None,
            "last_full_refresh": None,
            "issues": {},
        }
        _save_cache_file(cache_file, cache_data)

        mock_cache_issue_manager._list_issues_no_error_handling.return_value = []

        get_all_cached_issues(
            RepoIdentifier.from_full_name("test/repo"),
            mock_cache_issue_manager,
            force_refresh=True,
        )

        # Verify saved cache has last_full_refresh set
        with cache_file.open("r") as f:
            saved = json.load(f)
        assert saved["last_full_refresh"] == "2025-12-31T12:00:00+00:00"

    @patch(
        "mcp_workspace.github_operations.issues.cache._get_cache_file_path",
    )
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_incremental_refresh_does_not_update_last_full_refresh(
        self,
        mock_now: Mock,
        mock_cache_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """Test that an incremental refresh does not update last_full_refresh."""
        now = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = now

        cache_file = tmp_path / "test.json"
        mock_cache_path.return_value = cache_file

        # Set up cache with recent last_checked and recent last_full_refresh
        # so incremental refresh triggers (not full)
        recent_time = "2025-12-31T11:58:00+00:00"  # 2 min ago
        original_full_refresh = "2025-12-31T10:00:00+00:00"  # 2 hours ago, < 24h
        cache_data: CacheData = {
            "last_checked": recent_time,
            "last_full_refresh": original_full_refresh,
            "updates_covered_through": "2025-12-31T11:00:00+00:00",
            "issues": {
                "1": {
                    "number": 1,
                    "state": "open",
                    "labels": [],
                    "updated_at": "2025-12-31T09:00:00Z",
                    "url": "https://github.com/test/repo/issues/1",
                    "title": "Test",
                    "body": "",
                    "assignees": [],
                    "user": "testuser",
                    "created_at": "2025-12-31T08:00:00Z",
                    "locked": False,
                    "author_association": "OWNER",
                }
            },
        }
        _save_cache_file(cache_file, cache_data)

        mock_cache_issue_manager._list_issues_no_error_handling.return_value = []

        get_all_cached_issues(
            RepoIdentifier.from_full_name("test/repo"), mock_cache_issue_manager
        )

        # Verify last_full_refresh is unchanged
        with cache_file.open("r") as f:
            saved = json.load(f)
        assert saved["last_full_refresh"] == original_full_refresh
        # But last_checked should be updated
        assert saved["last_checked"] == "2025-12-31T12:00:00+00:00"

    @patch(
        "mcp_workspace.github_operations.issues.cache._get_cache_file_path",
    )
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_full_refresh_triggers_when_last_full_refresh_is_old(
        self,
        mock_now: Mock,
        mock_cache_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """Test that full refresh triggers when last_full_refresh is older than threshold."""
        now = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = now

        cache_file = tmp_path / "test.json"
        mock_cache_path.return_value = cache_file

        # Recent last_checked (2 min ago, outside 60s duplicate protection) but old last_full_refresh (25 hours ago)
        cache_data: CacheData = {
            "last_checked": "2025-12-31T11:58:00+00:00",
            "last_full_refresh": "2025-12-30T11:00:00+00:00",  # 25 hours ago
            "updates_covered_through": "2025-12-31T11:00:00+00:00",
            "issues": {
                "1": {
                    "number": 1,
                    "state": "open",
                    "labels": [],
                    "updated_at": "2025-12-31T09:00:00Z",
                    "url": "https://github.com/test/repo/issues/1",
                    "title": "Test",
                    "body": "",
                    "assignees": [],
                    "user": "testuser",
                    "created_at": "2025-12-31T08:00:00Z",
                    "locked": False,
                    "author_association": "OWNER",
                }
            },
        }
        _save_cache_file(cache_file, cache_data)

        mock_cache_issue_manager._list_issues_no_error_handling.return_value = []

        get_all_cached_issues(
            RepoIdentifier.from_full_name("test/repo"), mock_cache_issue_manager
        )

        # Full refresh should have been called with state="open" (not state="all" with since=)
        mock_cache_issue_manager._list_issues_no_error_handling.assert_called_once_with(
            state="open", include_pull_requests=False
        )

    @staticmethod
    def _issue(number: int, state: str = "open", title: str = "Test") -> IssueData:
        """Create a minimal IssueData for testing."""
        return IssueData(
            number=number,
            state=state,
            labels=[],
            updated_at="2025-12-31T09:00:00Z",
            url=f"https://github.com/test/repo/issues/{number}",
            title=title,
            body="",
            assignees=[],
            user="testuser",
            created_at="2025-12-31T08:00:00Z",
            locked=False,
            author_association="OWNER",
        )

    def _run_full_refresh(
        self,
        cache_file: Path,
        manager: Mock,
        issues: Dict[str, IssueData],
        cached_at: Dict[str, str],
        additional_issues: List[int],
    ) -> List[IssueData]:
        """Run get_all_cached_issues on a cache whose last full refresh is 25 h old."""
        cache_data: CacheData = {
            "last_checked": "2025-12-31T11:58:00+00:00",
            "last_full_refresh": "2025-12-30T11:00:00+00:00",  # 25 hours ago
            "updates_covered_through": "2025-12-31T11:00:00+00:00",
            "cached_at": cached_at,
            "issues": issues,
        }
        _save_cache_file(cache_file, cache_data)
        with (
            patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path",
                return_value=cache_file,
            ),
            patch(
                "mcp_workspace.github_operations.issues.cache.now_utc",
                return_value=datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc),
            ),
        ):
            return get_all_cached_issues(
                RepoIdentifier.from_full_name("test/repo"),
                manager,
                additional_issues=additional_issues,
            )

    def test_full_refresh_keeps_rechecked_closed_session_issue(
        self, tmp_path: Path, mock_cache_issue_manager: Mock
    ) -> None:
        """Full refresh re-checks a cached closed session issue once and keeps it.

        Non-session issues missing from the open list are still dropped.
        """
        cache_file = tmp_path / "test.json"
        old_stamp = "2025-12-31T11:00:00+00:00"
        closed_session = self._issue(123, "closed", "Closed session issue")
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = []
        mock_cache_issue_manager.get_issue.return_value = closed_session

        result = self._run_full_refresh(
            cache_file,
            mock_cache_issue_manager,
            {"1": self._issue(1), "123": closed_session},
            {"1": old_stamp, "123": old_stamp},
            [123],
        )

        mock_cache_issue_manager._list_issues_no_error_handling.assert_called_once_with(
            state="open", include_pull_requests=False
        )
        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
        assert result == [closed_session]

        with cache_file.open("r") as f:
            saved = json.load(f)
        assert saved["issues"] == {"123": closed_session}
        assert saved["cached_at"] == {"123": "2025-12-31T12:00:00+00:00"}

    def test_full_refresh_drops_deleted_session_issue(
        self, tmp_path: Path, mock_cache_issue_manager: Mock
    ) -> None:
        """Cached session issue now 404 (get_issue → number 0) → gone from cache."""
        cache_file = tmp_path / "test.json"
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = []
        mock_cache_issue_manager.get_issue.return_value = self._issue(0)

        result = self._run_full_refresh(
            cache_file,
            mock_cache_issue_manager,
            {"123": self._issue(123)},
            {"123": "2025-12-31T11:00:00+00:00"},
            [123],
        )

        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
        assert result == []
        with cache_file.open("r") as f:
            saved = json.load(f)
        assert "123" not in saved["issues"]
        assert "123" not in saved["cached_at"]

    def test_full_refresh_drops_transferred_session_issue(
        self, tmp_path: Path, mock_cache_issue_manager: Mock
    ) -> None:
        """Cached session issue transferred (IssueIdentityMismatchError) → gone."""
        cache_file = tmp_path / "test.json"
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = []
        mock_cache_issue_manager.get_issue.side_effect = IssueIdentityMismatchError(
            "issue #123 now belongs to other/repo"
        )

        result = self._run_full_refresh(
            cache_file,
            mock_cache_issue_manager,
            {"123": self._issue(123)},
            {"123": "2025-12-31T11:00:00+00:00"},
            [123],
        )

        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
        assert result == []
        with cache_file.open("r") as f:
            saved = json.load(f)
        assert "123" not in saved["issues"]
        assert "123" not in saved["cached_at"]

    def test_full_refresh_recheck_failure_keeps_cached_copy(
        self, tmp_path: Path, mock_cache_issue_manager: Mock
    ) -> None:
        """Transient re-check failure → cached copy and old stamp kept."""
        cache_file = tmp_path / "test.json"
        old_stamp = "2025-12-31T11:00:00+00:00"
        closed_session = self._issue(123, "closed")
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = []
        mock_cache_issue_manager.get_issue.side_effect = ConnectionError("down")

        result = self._run_full_refresh(
            cache_file,
            mock_cache_issue_manager,
            {"123": closed_session},
            {"123": old_stamp},
            [123],
        )

        assert result == [closed_session]
        with cache_file.open("r") as f:
            saved = json.load(f)
        assert saved["cached_at"] == {"123": old_stamp}

    def test_full_refresh_due_skips_stale_open_session_fetches(
        self, tmp_path: Path, mock_cache_issue_manager: Mock
    ) -> None:
        """Past cache_refresh_minutes: stale cached open session issues → zero get_issue."""
        cache_file = tmp_path / "test.json"
        stale_stamp = "2025-12-30T11:00:00+00:00"  # from the last full refresh
        numbers = [101, 102, 103]
        listed = [self._issue(n, title="Listed") for n in numbers]
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = listed

        result = self._run_full_refresh(
            cache_file,
            mock_cache_issue_manager,
            {str(n): self._issue(n, title="Cached") for n in numbers},
            {str(n): stale_stamp for n in numbers},
            numbers,
        )

        mock_cache_issue_manager.get_issue.assert_not_called()
        assert sorted(i["number"] for i in result) == numbers
        with cache_file.open("r") as f:
            saved = json.load(f)
        assert saved["cached_at"] == {
            str(n): "2025-12-31T12:00:00+00:00" for n in numbers
        }

    @patch(
        "mcp_workspace.github_operations.issues.cache._get_cache_file_path",
    )
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    def test_full_refresh_prefers_fresh_list_version_of_session_issue(
        self,
        mock_now: Mock,
        mock_cache_path: Mock,
        tmp_path: Path,
        mock_cache_issue_manager: Mock,
    ) -> None:
        """Session issue in the open list → saved entry is the listed version, stamped now."""
        mock_now.return_value = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
        cache_file = tmp_path / "test.json"
        mock_cache_path.return_value = cache_file

        cache_data: CacheData = {
            "last_checked": "2025-12-31T11:58:00+00:00",
            "last_full_refresh": "2025-12-30T11:00:00+00:00",  # 25 hours ago
            "updates_covered_through": "2025-12-31T11:00:00+00:00",
            "cached_at": {"123": "2025-12-31T11:00:00+00:00"},
            "issues": {"123": self._issue(123, title="Cached version")},
        }
        _save_cache_file(cache_file, cache_data)

        listed = self._issue(123, title="Listed version")
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = [listed]

        get_all_cached_issues(
            RepoIdentifier.from_full_name("test/repo"),
            mock_cache_issue_manager,
            additional_issues=[123],
        )

        mock_cache_issue_manager.get_issue.assert_not_called()
        with cache_file.open("r") as f:
            saved = json.load(f)
        assert saved["issues"]["123"] == listed
        assert saved["cached_at"]["123"] == "2025-12-31T12:00:00+00:00"

    def test_load_cache_without_last_full_refresh_field(self, tmp_path: Path) -> None:
        """Test backward compatibility: loading cache without last_full_refresh field."""
        cache_file = tmp_path / "test.json"
        # Write a cache file without the last_full_refresh field (old format)
        old_cache = {
            "last_checked": "2025-12-31T10:30:00Z",
            "issues": {"1": {"number": 1, "state": "open", "labels": []}},
        }
        with cache_file.open("w") as f:
            json.dump(old_cache, f)

        loaded = _load_cache_file(cache_file)
        assert loaded["last_full_refresh"] is None
        assert loaded["last_checked"] == "2025-12-31T10:30:00Z"
        assert "1" in loaded["issues"]
