"""Tests for issue cache functionality — file I/O and metrics.

Split from the original test_issue_cache.py by whole test class.
"""

import json
import logging
import os
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
        self, sample_cache_data: CacheData, tmp_path: Path
    ) -> None:
        """Test cache file save handles temp-file creation errors gracefully."""
        cache_path = tmp_path / "cache.json"
        with patch(
            "mcp_workspace.github_operations.issues.cache.tempfile.mkstemp",
            side_effect=PermissionError("Access denied"),
        ):
            result = _save_cache_file(cache_path, sample_cache_data)
        assert result is False
        assert not cache_path.exists()


class TestSaveCacheFileAtomicity:
    """Tests for unique temp files, cleanup and replace retry in _save_cache_file."""

    _REPLACE = "mcp_workspace.github_operations.issues.cache.os.replace"
    _SLEEP = "mcp_workspace.github_operations.issues.cache.time.sleep"

    def test_unique_temp_paths_in_target_directory(
        self, sample_cache_data: CacheData, tmp_path: Path
    ) -> None:
        """Two saves use different temp files next to the target."""
        cache_path = tmp_path / "x.issues.json"
        sources: List[str] = []
        real_replace = os.replace

        def recording_replace(src: str, dst: Any) -> None:
            sources.append(src)
            real_replace(src, dst)

        with patch(self._REPLACE, side_effect=recording_replace):
            assert _save_cache_file(cache_path, sample_cache_data) is True
            assert _save_cache_file(cache_path, sample_cache_data) is True

        assert len(sources) == 2
        assert sources[0] != sources[1]
        for src in sources:
            src_path = Path(src)
            assert src_path.parent == tmp_path
            assert src_path.name != "x.issues.tmp"
            assert src_path.name.endswith(".tmp")
        assert list(tmp_path.glob("*.tmp")) == []

    def test_write_failure_cleans_up_temp_file(
        self, sample_cache_data: CacheData, tmp_path: Path
    ) -> None:
        """A failing json.dump returns False and leaves no temp file."""
        cache_path = tmp_path / "x.issues.json"
        with patch(
            "mcp_workspace.github_operations.issues.cache.json.dump",
            side_effect=OSError("disk full"),
        ):
            result = _save_cache_file(cache_path, sample_cache_data)

        assert result is False
        assert list(tmp_path.glob("*.tmp")) == []
        assert not cache_path.exists()

    def test_replace_fails_once_then_succeeds(
        self, sample_cache_data: CacheData, tmp_path: Path
    ) -> None:
        """One transient os.replace failure is retried after a sleep."""
        cache_path = tmp_path / "x.issues.json"
        real_replace = os.replace
        calls = {"n": 0}

        def flaky_replace(src: str, dst: Any) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError("locked")
            real_replace(src, dst)

        with (
            patch(self._REPLACE, side_effect=flaky_replace),
            patch(self._SLEEP) as mock_sleep,
        ):
            result = _save_cache_file(cache_path, sample_cache_data)

        assert result is True
        assert mock_sleep.call_count == 1
        assert json.loads(cache_path.read_text()) == sample_cache_data
        assert list(tmp_path.glob("*.tmp")) == []

    def test_replace_fails_twice_returns_false(
        self,
        sample_cache_data: CacheData,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Two os.replace failures return False, log a warning, clean up."""
        caplog.set_level(
            logging.WARNING, logger="mcp_workspace.github_operations.issues.cache"
        )
        cache_path = tmp_path / "x.issues.json"

        with (
            patch(self._REPLACE, side_effect=PermissionError("locked")) as mock_rep,
            patch(self._SLEEP) as mock_sleep,
        ):
            result = _save_cache_file(cache_path, sample_cache_data)

        assert result is False
        assert mock_rep.call_count == 2
        assert mock_sleep.call_count == 1
        assert "Cache save error" in caplog.text
        assert list(tmp_path.glob("*.tmp")) == []
        assert not cache_path.exists()


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
                "author_association": "OWNER",
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
                "author_association": "OWNER",
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
                "author_association": "OWNER",
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
                "author_association": "OWNER",
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
                "author_association": "OWNER",
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
                "author_association": "OWNER",
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
                "author_association": "OWNER",
                "title": "Test",
                "body": "Test",
                "url": "http://test.com",
                "updated_at": "2025-12-31T08:00:00Z",
            }
        }

        _log_stale_cache_entries(cached_issues, fresh_issues)

        # Should not log anything for unchanged issues
        assert "Issue #123:" not in caplog.text
