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
