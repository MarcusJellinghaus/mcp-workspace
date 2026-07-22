"""Tests for issue cache functionality — file I/O and metrics.

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


class TestCacheMetricsLogging:
    """Tests for _log_cache_metrics function."""

    def test_log_cache_metrics_hit(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test cache hit metrics logging."""
        caplog.set_level(
            logging.DEBUG, logger="mcp_workspace.github_operations.issues.cache"
        )

        _log_cache_metrics("hit", "test-repo", age_minutes=15, issue_count=5)

        assert "Cache hit for test-repo: age=15m, issues=5" in caplog.text

    def test_log_cache_metrics_miss(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test cache miss metrics logging."""
        caplog.set_level(
            logging.DEBUG, logger="mcp_workspace.github_operations.issues.cache"
        )

        _log_cache_metrics("miss", "test-repo", reason="no_cache")

        assert "Cache miss for test-repo: reason='no_cache'" in caplog.text

    def test_log_cache_metrics_refresh(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test cache refresh metrics logging."""
        caplog.set_level(
            logging.DEBUG, logger="mcp_workspace.github_operations.issues.cache"
        )

        _log_cache_metrics("refresh", "test-repo", refresh_type="full", issue_count=10)

        assert "Cache refresh for test-repo: type=full, new_issues=10" in caplog.text

    def test_log_cache_metrics_save(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test cache save metrics logging."""
        caplog.set_level(
            logging.DEBUG, logger="mcp_workspace.github_operations.issues.cache"
        )

        _log_cache_metrics("save", "test-repo", total_issues=25)

        assert "Cache save for test-repo: total_issues=25" in caplog.text


class TestCacheFilePath:
    """Tests for _get_cache_file_path function."""

    def test_get_cache_file_path_basic(self) -> None:
        """Test basic cache file path generation."""
        repo_identifier = RepoIdentifier.from_full_name("owner/repo")
        path = _get_cache_file_path(repo_identifier)

        expected_dir = get_user_app_data_dir("mcp_coder") / "coordinator_cache"
        expected_file = expected_dir / "github_com_owner_repo.issues.json"

        assert path == expected_file

    def test_get_cache_file_path_complex_names(self) -> None:
        """Test cache file path with complex repository names."""
        test_cases = [
            ("anthropics/claude-code", "github_com_anthropics_claude-code.issues.json"),
            ("user/repo-with-dashes", "github_com_user_repo-with-dashes.issues.json"),
            (
                "org/very.long.repo.name",
                "github_com_org_very.long.repo.name.issues.json",
            ),
        ]

        for full_name, expected_filename in test_cases:
            repo_identifier = RepoIdentifier.from_full_name(full_name)
            path = _get_cache_file_path(repo_identifier)
            assert path.name == expected_filename


class TestCacheFileOperations:
    """Tests for cache file load/save operations."""

    def test_load_cache_file_nonexistent(self) -> None:
        """Test loading non-existent cache file returns empty structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "nonexistent.json"
            result = _load_cache_file(cache_path)

            assert result == {
                "last_checked": None,
                "last_full_refresh": None,
                "updates_covered_through": None,
                "cached_at": {},
                "version": None,
                "issues": {},
            }

    def test_load_cache_file_valid(self, sample_cache_data: CacheData) -> None:
        """Test loading valid cache file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache_path.write_text(json.dumps(sample_cache_data))

            result = _load_cache_file(cache_path)
            # cached_at / version are surfaced with safe defaults for old-shape
            # data; updates_covered_through is present in the fixture and round-trips.
            expected: CacheData = {
                **sample_cache_data,
                "cached_at": {},
                "version": None,
            }
            assert result == expected

    def test_load_cache_file_invalid_json(self) -> None:
        """Test loading corrupted JSON file returns empty structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "invalid.json"
            cache_path.write_text("invalid json content")

            result = _load_cache_file(cache_path)
            assert result == {
                "last_checked": None,
                "last_full_refresh": None,
                "updates_covered_through": None,
                "cached_at": {},
                "version": None,
                "issues": {},
            }

    def test_load_cache_file_invalid_structure(self) -> None:
        """Test loading file with invalid structure returns empty structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "invalid_structure.json"
            cache_path.write_text('{"wrong_key": "value"}')

            result = _load_cache_file(cache_path)
            assert result == {
                "last_checked": None,
                "last_full_refresh": None,
                "updates_covered_through": None,
                "cached_at": {},
                "version": None,
                "issues": {},
            }

    def test_save_cache_file_success(self, sample_cache_data: CacheData) -> None:
        """Test successful cache file save with atomic write."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "subdir" / "cache.json"

            result = _save_cache_file(cache_path, sample_cache_data)
            assert result is True

            # Verify file was created and data is correct
            assert cache_path.exists()
            saved_data = json.loads(cache_path.read_text())
            assert saved_data == sample_cache_data

    def test_save_cache_file_creates_directory(
        self, sample_cache_data: CacheData
    ) -> None:
        """Test cache file save creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "deep" / "nested" / "dirs" / "cache.json"

            result = _save_cache_file(cache_path, sample_cache_data)
            assert result is True
            assert cache_path.exists()

    def test_save_cache_file_permission_error(
        self, sample_cache_data: CacheData
    ) -> None:
        """Test cache file save handles permission errors gracefully."""
        with patch.object(Path, "open", side_effect=PermissionError("Access denied")):
            cache_path = Path("/fake/path/cache.json")
            result = _save_cache_file(cache_path, sample_cache_data)
            assert result is False


class TestStalenessLogging:
    """Tests for _log_stale_cache_entries function."""

    def test_log_stale_cache_entries_state_change(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test logging when issue state changes."""
        caplog.set_level(
            logging.INFO, logger="mcp_workspace.github_operations.issues.cache"
        )

        cached_issues: Dict[str, IssueData] = {
            "123": {
                "number": 123,
                "state": "open",
                "labels": ["bug"],
                "assignees": [],
                "user": "testuser",
                "created_at": "2025-12-31T08:00:00Z",
                "locked": False,
                "title": "Test",
                "body": "Test",
                "url": "http://test.com",
                "updated_at": "2025-12-31T08:00:00Z",
            }
        }
        fresh_issues: Dict[str, IssueData] = {
            "123": {
                "number": 123,
                "state": "closed",
                "labels": ["bug"],
                "assignees": [],
                "user": "testuser",
                "created_at": "2025-12-31T08:00:00Z",
                "locked": False,
                "title": "Test",
                "body": "Test",
                "url": "http://test.com",
                "updated_at": "2025-12-31T08:00:00Z",
            }
        }

        _log_stale_cache_entries(cached_issues, fresh_issues)

        assert "Issue #123: cached state 'open' != actual 'closed'" in caplog.text

    def test_log_stale_cache_entries_label_change(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test logging when issue labels change."""
        caplog.set_level(
            logging.INFO, logger="mcp_workspace.github_operations.issues.cache"
        )

        cached_issues: Dict[str, IssueData] = {
            "123": {
                "number": 123,
                "state": "open",
                "labels": ["status-02:awaiting-planning"],
                "assignees": [],
                "user": "testuser",
                "created_at": "2025-12-31T08:00:00Z",
                "locked": False,
                "title": "Test",
                "body": "Test",
                "url": "http://test.com",
                "updated_at": "2025-12-31T08:00:00Z",
            }
        }
        fresh_issues: Dict[str, IssueData] = {
            "123": {
                "number": 123,
                "state": "open",
                "labels": ["status-03:planning"],
                "assignees": [],
                "user": "testuser",
                "created_at": "2025-12-31T08:00:00Z",
                "locked": False,
                "title": "Test",
                "body": "Test",
                "url": "http://test.com",
                "updated_at": "2025-12-31T08:00:00Z",
            }
        }

        _log_stale_cache_entries(cached_issues, fresh_issues)

        assert "Issue #123: cached labels" in caplog.text
        assert "status-02:awaiting-planning" in caplog.text
        assert "status-03:planning" in caplog.text

    def test_log_stale_cache_entries_missing_issue(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test logging when cached issue no longer exists."""
        caplog.set_level(
            logging.INFO, logger="mcp_workspace.github_operations.issues.cache"
        )

        cached_issues: Dict[str, IssueData] = {
            "123": {
                "number": 123,
                "state": "open",
                "labels": ["bug"],
                "assignees": [],
                "user": "testuser",
                "created_at": "2025-12-31T08:00:00Z",
                "locked": False,
                "title": "Test",
                "body": "Test",
                "url": "http://test.com",
                "updated_at": "2025-12-31T08:00:00Z",
            }
        }
        fresh_issues: Dict[str, IssueData] = {}

        _log_stale_cache_entries(cached_issues, fresh_issues)

        assert "Issue #123: no longer exists in repository" in caplog.text

    def test_log_stale_cache_entries_no_changes(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test no logging when no changes detected."""
        cached_issues: Dict[str, IssueData] = {
            "123": {
                "number": 123,
                "state": "open",
                "labels": ["bug"],
                "assignees": [],
                "user": "testuser",
                "created_at": "2025-12-31T08:00:00Z",
                "locked": False,
                "title": "Test",
                "body": "Test",
                "url": "http://test.com",
                "updated_at": "2025-12-31T08:00:00Z",
            }
        }
        fresh_issues: Dict[str, IssueData] = {
            "123": {
                "number": 123,
                "state": "open",
                "labels": ["bug"],
                "assignees": [],
                "user": "testuser",
                "created_at": "2025-12-31T08:00:00Z",
                "locked": False,
                "title": "Test",
                "body": "Test",
                "url": "http://test.com",
                "updated_at": "2025-12-31T08:00:00Z",
            }
        }

        _log_stale_cache_entries(cached_issues, fresh_issues)

        # Should not log anything for unchanged issues
        assert "Issue #123:" not in caplog.text
