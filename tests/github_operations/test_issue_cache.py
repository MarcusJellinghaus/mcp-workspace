"""Tests for issue cache functionality.

Tests the get_all_cached_issues() function and its helper functions
for proper cache storage, duplicate protection, and incremental fetching.
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


class TestCacheIssueUpdate:
    """Tests for update_issue_labels_in_cache function."""

    def test_update_issue_labels_success(self) -> None:
        """Test successful label update for existing issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.json"

            # Create initial cache with issue
            initial_cache = {
                "last_checked": "2025-01-03T10:30:00Z",
                "issues": {
                    "123": {
                        "number": 123,
                        "state": "open",
                        "labels": ["status-02:awaiting-planning", "bug"],
                        "updated_at": "2025-01-03T09:00:00Z",
                        "url": "https://github.com/test/repo/issues/123",
                        "title": "Test issue",
                        "body": "Test issue body",
                        "assignees": [],
                        "user": "testuser",
                        "created_at": "2025-01-03T08:00:00Z",
                        "locked": False,
                    }
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            # Mock _get_cache_file_path to return our test path
            with patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path:
                mock_path.return_value = cache_path

                # Call the function under test
                update_issue_labels_in_cache(
                    RepoIdentifier.from_full_name("test/repo"),
                    123,
                    "status-02:awaiting-planning",
                    "status-03:planning",
                )

            # Verify cache was updated
            updated_cache = json.loads(cache_path.read_text())
            issue_labels = updated_cache["issues"]["123"]["labels"]

            assert "status-02:awaiting-planning" not in issue_labels
            assert "status-03:planning" in issue_labels
            assert "bug" in issue_labels  # Other labels preserved

    def test_update_issue_labels_remove_only(self) -> None:
        """Test removing a label without adding new one."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.json"

            # Create cache with multiple labels
            initial_cache = {
                "last_checked": "2025-01-03T10:30:00Z",
                "issues": {
                    "456": {
                        "number": 456,
                        "state": "open",
                        "labels": ["status-05:plan-ready", "enhancement", "urgent"],
                        "updated_at": "2025-01-03T09:00:00Z",
                        "url": "https://github.com/test/repo/issues/456",
                        "title": "Enhancement issue",
                        "body": "Enhancement body",
                        "assignees": [],
                        "user": "testuser",
                        "created_at": "2025-01-03T08:00:00Z",
                        "locked": False,
                    }
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            with patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path:
                mock_path.return_value = cache_path

                # Remove label without adding new one (empty string)
                update_issue_labels_in_cache(
                    RepoIdentifier.from_full_name("test/repo"),
                    456,
                    "status-05:plan-ready",
                    "",
                )

            # Verify only the specified label was removed
            updated_cache = json.loads(cache_path.read_text())
            issue_labels = updated_cache["issues"]["456"]["labels"]

            assert "status-05:plan-ready" not in issue_labels
            assert "enhancement" in issue_labels
            assert "urgent" in issue_labels

    def test_update_issue_labels_add_only(self) -> None:
        """Test adding a label without removing existing ones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.json"

            initial_cache = {
                "last_checked": "2025-01-03T10:30:00Z",
                "issues": {
                    "789": {
                        "number": 789,
                        "state": "open",
                        "labels": ["bug"],
                        "updated_at": "2025-01-03T09:00:00Z",
                        "url": "https://github.com/test/repo/issues/789",
                        "title": "Bug issue",
                        "body": "Bug body",
                        "assignees": [],
                        "user": "testuser",
                        "created_at": "2025-01-03T08:00:00Z",
                        "locked": False,
                    }
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            with patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path:
                mock_path.return_value = cache_path

                # Add new label without removing any (empty old_label)
                update_issue_labels_in_cache(
                    RepoIdentifier.from_full_name("test/repo"),
                    789,
                    "",
                    "status-02:awaiting-planning",
                )

            # Verify new label was added and existing preserved
            updated_cache = json.loads(cache_path.read_text())
            issue_labels = updated_cache["issues"]["789"]["labels"]

            assert "bug" in issue_labels
            assert "status-02:awaiting-planning" in issue_labels

    def test_update_issue_labels_missing_issue(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test graceful handling when issue not found in cache."""
        caplog.set_level(
            logging.WARNING, logger="mcp_workspace.github_operations.issues.cache"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.json"

            # Create cache without the target issue
            initial_cache = {
                "last_checked": "2025-01-03T10:30:00Z",
                "issues": {
                    "456": {
                        "number": 456,
                        "state": "open",
                        "labels": ["bug"],
                        "updated_at": "2025-01-03T09:00:00Z",
                        "url": "https://github.com/test/repo/issues/456",
                        "title": "Other issue",
                        "body": "Other body",
                        "assignees": [],
                        "user": "testuser",
                        "created_at": "2025-01-03T08:00:00Z",
                        "locked": False,
                    }
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            with patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path:
                mock_path.return_value = cache_path

                # Try to update non-existent issue - should not raise exception
                update_issue_labels_in_cache(
                    RepoIdentifier.from_full_name("test/repo"),
                    123,
                    "old-label",
                    "new-label",
                )

            # Verify appropriate warning was logged
            assert "Issue #123 not found in cache for test/repo" in caplog.text

            # Verify cache remained unchanged
            updated_cache = json.loads(cache_path.read_text())
            assert "123" not in updated_cache["issues"]
            assert updated_cache["issues"]["456"]["labels"] == ["bug"]

    def test_update_issue_labels_invalid_cache_structure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test handling of corrupted cache file structure."""
        caplog.set_level(
            logging.WARNING, logger="mcp_workspace.github_operations.issues.cache"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.json"

            # Create invalid cache structure
            invalid_cache = {"wrong_structure": "invalid"}
            cache_path.write_text(json.dumps(invalid_cache))

            with patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path:
                mock_path.return_value = cache_path

                # Should handle gracefully without crashing
                update_issue_labels_in_cache(
                    RepoIdentifier.from_full_name("test/repo"),
                    123,
                    "old-label",
                    "new-label",
                )

            # Verify warning was logged
            assert (
                "Invalid cache structure" in caplog.text
                or "Unexpected error updating cache" in caplog.text
            )

    def test_update_issue_labels_file_permission_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test handling of file permission errors."""
        caplog.set_level(
            logging.WARNING, logger="mcp_workspace.github_operations.issues.cache"
        )

        with (
            patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path,
            patch(
                "mcp_workspace.github_operations.issues.cache._load_cache_file"
            ) as mock_load,
            patch(
                "mcp_workspace.github_operations.issues.cache._save_cache_file"
            ) as mock_save,
        ):
            mock_path.return_value = Path("/fake/cache.json")
            mock_load.return_value = {
                "last_checked": "2025-01-03T10:30:00Z",
                "issues": {
                    "123": {
                        "number": 123,
                        "labels": ["old-label"],
                        "state": "open",
                        "updated_at": "2025-01-03T09:00:00Z",
                        "url": "https://github.com/test/repo/issues/123",
                        "title": "Test",
                        "body": "Test",
                        "assignees": [],
                        "user": "testuser",
                        "created_at": "2025-01-03T08:00:00Z",
                        "locked": False,
                    }
                },
            }
            mock_save.return_value = False  # Simulate save failure

            # Should handle save failure gracefully
            update_issue_labels_in_cache(
                RepoIdentifier.from_full_name("test/repo"),
                123,
                "old-label",
                "new-label",
            )

            # Verify appropriate warning was logged
            assert any(
                "Cache update failed" in record.message for record in caplog.records
            )

    def test_update_issue_labels_logging(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test proper logging behavior during successful updates."""
        caplog.set_level(
            logging.DEBUG, logger="mcp_workspace.github_operations.issues.cache"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.json"

            initial_cache = {
                "last_checked": "2025-01-03T10:30:00Z",
                "issues": {
                    "123": {
                        "number": 123,
                        "state": "open",
                        "labels": ["status-02:awaiting-planning"],
                        "updated_at": "2025-01-03T09:00:00Z",
                        "url": "https://github.com/test/repo/issues/123",
                        "title": "Test issue",
                        "body": "Test body",
                        "assignees": [],
                        "user": "testuser",
                        "created_at": "2025-01-03T08:00:00Z",
                        "locked": False,
                    }
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            with patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path:
                mock_path.return_value = cache_path

                update_issue_labels_in_cache(
                    RepoIdentifier.from_full_name("test/repo"),
                    123,
                    "status-02:awaiting-planning",
                    "status-03:planning",
                )

            # Verify debug logging includes key operation details
            log_messages = [
                record.message
                for record in caplog.records
                if record.levelname == "DEBUG"
            ]
            assert any(
                "Updated issue #123 labels in cache" in msg for msg in log_messages
            )
            assert any("status-02:awaiting-planning" in msg for msg in log_messages)
            assert any("status-03:planning" in msg for msg in log_messages)
            # Verify ASCII arrow is used
            assert any("->" in msg for msg in log_messages)


class TestCacheUpdateIntegration:
    """Integration tests for cache update in dispatch workflow."""

    def test_dispatch_workflow_updates_cache(self) -> None:
        """Test that cache update integration exists and works correctly.

        This test verifies the cache update functionality without mocking,
        since the integration between dispatch_workflow and cache update
        already exists in the coordinator.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.json"

            # Create initial cache with issue that has a workflow label
            initial_cache = {
                "last_checked": "2025-01-03T10:30:00Z",
                "issues": {
                    "123": {
                        "number": 123,
                        "state": "open",
                        "labels": ["status-02:awaiting-planning"],
                        "updated_at": "2025-01-03T09:00:00Z",
                        "url": "https://github.com/test/repo/issues/123",
                        "title": "Test issue",
                        "body": "Test body",
                        "assignees": [],
                        "user": "testuser",
                        "created_at": "2025-01-03T08:00:00Z",
                        "locked": False,
                    }
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            # Mock only the cache file path to point to our test cache
            with patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path:
                mock_path.return_value = cache_path

                # Call the actual cache update function (this is what dispatch_workflow calls)
                update_issue_labels_in_cache(
                    RepoIdentifier.from_full_name("test/repo"),
                    123,
                    "status-02:awaiting-planning",
                    "status-03:planning",
                )

            # Verify the cache was actually updated
            updated_cache = json.loads(cache_path.read_text())
            issue_labels = updated_cache["issues"]["123"]["labels"]

            # Check that the old label was removed and new label was added
            assert "status-02:awaiting-planning" not in issue_labels
            assert "status-03:planning" in issue_labels

    def test_multiple_dispatches_update_cache_correctly(self) -> None:
        """Test multiple dispatch operations update cache sequentially."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.json"

            # Create cache with multiple issues
            initial_cache = {
                "last_checked": "2025-01-03T10:30:00Z",
                "issues": {
                    "123": {
                        "number": 123,
                        "state": "open",
                        "labels": ["status-02:awaiting-planning"],
                        "updated_at": "2025-01-03T09:00:00Z",
                        "url": "https://github.com/test/repo/issues/123",
                        "title": "Issue 1",
                        "body": "Body 1",
                        "assignees": [],
                        "user": "testuser",
                        "created_at": "2025-01-03T08:00:00Z",
                        "locked": False,
                    },
                    "456": {
                        "number": 456,
                        "state": "open",
                        "labels": ["status-05:plan-ready"],
                        "updated_at": "2025-01-03T09:00:00Z",
                        "url": "https://github.com/test/repo/issues/456",
                        "title": "Issue 2",
                        "body": "Body 2",
                        "assignees": [],
                        "user": "testuser",
                        "created_at": "2025-01-03T08:00:00Z",
                        "locked": False,
                    },
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            with patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path:
                mock_path.return_value = cache_path

                # Simulate multiple dispatch operations
                update_issue_labels_in_cache(
                    RepoIdentifier.from_full_name("test/repo"),
                    123,
                    "status-02:awaiting-planning",
                    "status-03:planning",
                )
                update_issue_labels_in_cache(
                    RepoIdentifier.from_full_name("test/repo"),
                    456,
                    "status-05:plan-ready",
                    "status-06:implementing",
                )

            # Verify both issues were updated correctly
            final_cache = json.loads(cache_path.read_text())

            issue_123_labels = final_cache["issues"]["123"]["labels"]
            assert "status-02:awaiting-planning" not in issue_123_labels
            assert "status-03:planning" in issue_123_labels

            issue_456_labels = final_cache["issues"]["456"]["labels"]
            assert "status-05:plan-ready" not in issue_456_labels
            assert "status-06:implementing" in issue_456_labels

    def test_cache_update_failure_does_not_break_dispatch(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that cache update failures don't interrupt dispatch workflow."""
        caplog.set_level(
            logging.WARNING, logger="mcp_workspace.github_operations.issues.cache"
        )

        with (
            patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path,
            patch(
                "mcp_workspace.github_operations.issues.cache._load_cache_file",
                side_effect=Exception("Cache error"),
            ),
        ):
            mock_path.return_value = Path("/nonexistent/cache.json")

            # Cache update failure should not raise exception
            try:
                update_issue_labels_in_cache(
                    RepoIdentifier.from_full_name("test/repo"),
                    123,
                    "old-label",
                    "new-label",
                )
                # Should complete without exception
            except Exception as e:  # pylint: disable=broad-exception-caught
                pytest.fail(f"Cache update failure should not break workflow: {e}")

            # Verify appropriate warning was logged but execution continued
            warning_messages = [
                record.message
                for record in caplog.records
                if record.levelname == "WARNING"
            ]
            assert any(
                "Cache update failed" in msg or "Cache error" in msg
                for msg in warning_messages
            )


class TestAdditionalIssuesParameter:
    """Tests for additional_issues parameter in get_all_cached_issues."""

    def test_additional_issues_fetched_and_cached(
        self, mock_cache_issue_manager: Mock
    ) -> None:
        """Test that additional issues are fetched via API and added to cache.

        Given: Cache has open issues, additional_issues=[123] where #123 is closed
        When: Call get_all_cached_issues(additional_issues=[123])
        Then:
        - Issue #123 is fetched via API
        - Issue #123 is in returned list
        - Issue #123 is saved to cache
        """
        from mcp_workspace.github_operations.issues.cache import get_all_cached_issues

        # Mock the open issues API call
        open_issue: IssueData = {
            "number": 100,
            "state": "open",
            "labels": ["bug"],
            "assignees": [],
            "user": "testuser",
            "created_at": "2025-12-31T08:00:00Z",
            "locked": False,
            "title": "Open issue",
            "body": "Open body",
            "url": "http://test.com/100",
            "updated_at": "2025-12-31T08:00:00Z",
        }

        # Mock the closed issue API call
        closed_issue: IssueData = {
            "number": 123,
            "state": "closed",
            "labels": ["bug"],
            "assignees": [],
            "user": "testuser",
            "created_at": "2025-12-31T07:00:00Z",
            "locked": False,
            "title": "Closed issue",
            "body": "Closed body",
            "url": "http://test.com/123",
            "updated_at": "2025-12-31T09:00:00Z",
        }

        mock_cache_issue_manager.list_issues.return_value = [open_issue]
        mock_cache_issue_manager.get_issue.return_value = closed_issue
        mock_cache_issue_manager.repo_url = "https://github.com/owner/repo"

        with (
            patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path,
            patch(
                "mcp_workspace.github_operations.issues.cache._load_cache_file"
            ) as mock_load,
            patch(
                "mcp_workspace.github_operations.issues.cache._save_cache_file"
            ) as mock_save,
        ):
            import tempfile
            from pathlib import Path

            mock_path.return_value = Path(tempfile.gettempdir()) / "test_cache.json"
            mock_load.return_value = {"last_checked": None, "issues": {}}
            mock_save.return_value = True

            # Call with additional_issues parameter
            result = get_all_cached_issues(
                RepoIdentifier.from_full_name("owner/repo"),
                mock_cache_issue_manager,
                additional_issues=[123],
            )

            # Verify issue #123 was fetched via get_issue
            mock_cache_issue_manager.get_issue.assert_called_once_with(123)

            # Verify both open and closed issues are in result
            assert len(result) == 2
            issue_numbers = {issue["number"] for issue in result}
            assert 100 in issue_numbers
            assert 123 in issue_numbers

            # Verify save was called (cache includes additional issue)
            assert mock_save.called
            saved_data = mock_save.call_args[0][1]
            assert "100" in saved_data["issues"]
            assert "123" in saved_data["issues"]

    def test_additional_issues_always_refreshed(
        self, mock_cache_issue_manager: Mock
    ) -> None:
        """Test that additional issues are always re-fetched for freshness.

        Given: Cache already has issue #123 with stale state (was open, now closed)
        When: Call get_all_cached_issues(additional_issues=[123])
        Then:
        - API call is made for #123 to get fresh data
        - Issue #123 is in returned list with updated state
        """
        from mcp_workspace.github_operations.issues.cache import get_all_cached_issues

        # Cached issue with stale state (open)
        existing_issue: IssueData = {
            "number": 123,
            "state": "open",  # Stale - was open, now closed
            "labels": ["bug"],
            "assignees": [],
            "user": "testuser",
            "created_at": "2025-12-31T07:00:00Z",
            "locked": False,
            "title": "Existing issue",
            "body": "Existing body",
            "url": "http://test.com/123",
            "updated_at": "2025-12-31T09:00:00Z",
        }

        # Fresh issue state from API (closed)
        fresh_issue: IssueData = {
            "number": 123,
            "state": "closed",  # Fresh - actually closed now
            "labels": ["bug"],
            "assignees": [],
            "user": "testuser",
            "created_at": "2025-12-31T07:00:00Z",
            "locked": False,
            "title": "Existing issue",
            "body": "Existing body",
            "url": "http://test.com/123",
            "updated_at": "2025-12-31T09:00:00Z",
        }

        mock_cache_issue_manager.list_issues.return_value = []
        mock_cache_issue_manager.repo_url = "https://github.com/owner/repo"
        mock_cache_issue_manager.get_issue.return_value = fresh_issue

        with (
            patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path,
            patch(
                "mcp_workspace.github_operations.issues.cache._load_cache_file"
            ) as mock_load,
            patch(
                "mcp_workspace.github_operations.issues.cache._save_cache_file"
            ) as mock_save,
        ):
            import tempfile
            from pathlib import Path

            mock_path.return_value = Path(tempfile.gettempdir()) / "test_cache.json"
            # Cache already has issue #123
            mock_load.return_value = {
                "last_checked": None,
                "issues": {"123": existing_issue},
            }
            mock_save.return_value = True

            # Call with additional_issues parameter
            result = get_all_cached_issues(
                RepoIdentifier.from_full_name("owner/repo"),
                mock_cache_issue_manager,
                additional_issues=[123],
            )

            # Verify get_issue WAS called to refresh data
            mock_cache_issue_manager.get_issue.assert_called_once_with(123)

            # Verify issue #123 is in result with FRESH state (closed)
            assert len(result) == 1
            assert result[0]["number"] == 123
            assert result[0]["state"] == "closed"  # Fresh state, not stale

    def test_no_additional_issues_backward_compatible(
        self, mock_cache_issue_manager: Mock
    ) -> None:
        """Test backward compatibility when additional_issues not provided.

        Given: Existing cache with open issues
        When: Call get_all_cached_issues() (without additional_issues)
        Then:
        - Behaves exactly as before
        - Only open issues returned
        """
        from mcp_workspace.github_operations.issues.cache import get_all_cached_issues

        open_issue: IssueData = {
            "number": 100,
            "state": "open",
            "labels": ["bug"],
            "assignees": [],
            "user": "testuser",
            "created_at": "2025-12-31T08:00:00Z",
            "locked": False,
            "title": "Open issue",
            "body": "Open body",
            "url": "http://test.com/100",
            "updated_at": "2025-12-31T08:00:00Z",
        }

        mock_cache_issue_manager.list_issues.return_value = [open_issue]
        mock_cache_issue_manager.repo_url = "https://github.com/owner/repo"

        with (
            patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path,
            patch(
                "mcp_workspace.github_operations.issues.cache._load_cache_file"
            ) as mock_load,
            patch(
                "mcp_workspace.github_operations.issues.cache._save_cache_file"
            ) as mock_save,
        ):
            import tempfile
            from pathlib import Path

            mock_path.return_value = Path(tempfile.gettempdir()) / "test_cache.json"
            mock_load.return_value = {"last_checked": None, "issues": {}}
            mock_save.return_value = True

            # Call WITHOUT additional_issues parameter
            result = get_all_cached_issues(
                RepoIdentifier.from_full_name("owner/repo"), mock_cache_issue_manager
            )

            # Verify get_issue was NOT called
            mock_cache_issue_manager.get_issue.assert_not_called()

            # Verify only open issues returned
            assert len(result) == 1
            assert result[0]["number"] == 100
            assert result[0]["state"] == "open"

    def test_additional_issues_with_api_failure(
        self, mock_cache_issue_manager: Mock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test graceful handling when API fails for additional issue.

        Given: API fails for issue #123
        When: Call get_all_cached_issues(additional_issues=[123])
        Then:
        - Warning logged
        - Other issues still returned
        - No exception raised
        """
        import logging

        from mcp_workspace.github_operations.issues.cache import get_all_cached_issues

        caplog.set_level(
            logging.WARNING, logger="mcp_workspace.github_operations.issues.cache"
        )

        open_issue: IssueData = {
            "number": 100,
            "state": "open",
            "labels": ["bug"],
            "assignees": [],
            "user": "testuser",
            "created_at": "2025-12-31T08:00:00Z",
            "locked": False,
            "title": "Open issue",
            "body": "Open body",
            "url": "http://test.com/100",
            "updated_at": "2025-12-31T08:00:00Z",
        }

        mock_cache_issue_manager.list_issues.return_value = [open_issue]
        mock_cache_issue_manager.get_issue.side_effect = Exception("API Error")
        mock_cache_issue_manager.repo_url = "https://github.com/owner/repo"

        with (
            patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path,
            patch(
                "mcp_workspace.github_operations.issues.cache._load_cache_file"
            ) as mock_load,
            patch(
                "mcp_workspace.github_operations.issues.cache._save_cache_file"
            ) as mock_save,
        ):
            import tempfile
            from pathlib import Path

            mock_path.return_value = Path(tempfile.gettempdir()) / "test_cache.json"
            mock_load.return_value = {"last_checked": None, "issues": {}}
            mock_save.return_value = True

            # Call with additional_issues - should not raise exception
            result = get_all_cached_issues(
                RepoIdentifier.from_full_name("owner/repo"),
                mock_cache_issue_manager,
                additional_issues=[123],
            )

            # Verify warning was logged
            assert "Failed to fetch issue #123" in caplog.text

            # Verify other issues still returned
            assert len(result) == 1
            assert result[0]["number"] == 100

    def test_additional_issues_empty_list(self, mock_cache_issue_manager: Mock) -> None:
        """Test that empty additional_issues list behaves as if not provided.

        Given: Cache with open issues
        When: Call get_all_cached_issues(additional_issues=[])
        Then:
        - Behaves as if parameter not provided
        - Only open issues returned
        """
        from mcp_workspace.github_operations.issues.cache import get_all_cached_issues

        open_issue: IssueData = {
            "number": 100,
            "state": "open",
            "labels": ["bug"],
            "assignees": [],
            "user": "testuser",
            "created_at": "2025-12-31T08:00:00Z",
            "locked": False,
            "title": "Open issue",
            "body": "Open body",
            "url": "http://test.com/100",
            "updated_at": "2025-12-31T08:00:00Z",
        }

        mock_cache_issue_manager.list_issues.return_value = [open_issue]
        mock_cache_issue_manager.repo_url = "https://github.com/owner/repo"

        with (
            patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path"
            ) as mock_path,
            patch(
                "mcp_workspace.github_operations.issues.cache._load_cache_file"
            ) as mock_load,
            patch(
                "mcp_workspace.github_operations.issues.cache._save_cache_file"
            ) as mock_save,
        ):
            import tempfile
            from pathlib import Path

            mock_path.return_value = Path(tempfile.gettempdir()) / "test_cache.json"
            mock_load.return_value = {"last_checked": None, "issues": {}}
            mock_save.return_value = True

            # Call with EMPTY additional_issues list
            result = get_all_cached_issues(
                RepoIdentifier.from_full_name("owner/repo"),
                mock_cache_issue_manager,
                additional_issues=[],
            )

            # Verify get_issue was NOT called
            mock_cache_issue_manager.get_issue.assert_not_called()

            # Verify only open issues returned
            assert len(result) == 1
            assert result[0]["number"] == 100


class TestApiFailureHandling:
    """Tests for API failure handling with snapshot restore in get_all_cached_issues()."""

    def _make_issue(self, number: int, title: str = "Test issue") -> IssueData:
        """Create a minimal IssueData for testing."""
        return IssueData(
            number=number,
            state="open",
            labels=["bug"],
            updated_at="2025-12-31T09:00:00Z",
            url=f"https://github.com/test/repo/issues/{number}",
            title=title,
            body="body",
            assignees=[],
            user="testuser",
            created_at="2025-12-31T08:00:00Z",
            locked=False,
        )

    @patch(
        "mcp_workspace.github_operations.issues.cache._save_cache_file",
        return_value=True,
    )
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    @patch("mcp_workspace.github_operations.issues.cache._load_cache_file")
    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    def test_api_failure_does_not_advance_last_checked(
        self,
        mock_get_path: Mock,
        mock_load: Mock,
        mock_now: Mock,
        mock_save: Mock,
        mock_cache_issue_manager: Mock,
        tmp_path: Path,
    ) -> None:
        """API failure should not advance last_checked in cache."""
        original_last_checked = "2025-12-31T10:00:00Z"
        cache_data: CacheData = {
            "last_checked": original_last_checked,
            "issues": {
                "1": self._make_issue(1),
            },
        }
        mock_get_path.return_value = tmp_path / "cache.json"
        mock_load.return_value = cache_data
        mock_now.return_value = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)

        # Simulate API failure
        from github import GithubException

        mock_cache_issue_manager._list_issues_no_error_handling.side_effect = (
            GithubException(500, "Server Error", headers={})
        )

        result = get_all_cached_issues(
            RepoIdentifier.from_full_name("test/repo"),
            mock_cache_issue_manager,
            force_refresh=True,
        )

        # last_checked should NOT have been advanced (no save call with new timestamp)
        # The function returns stale data without saving
        mock_save.assert_not_called()
        # Should still return the stale issue
        assert len(result) == 1
        assert result[0]["number"] == 1

    @patch(
        "mcp_workspace.github_operations.issues.cache._save_cache_file",
        return_value=True,
    )
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    @patch("mcp_workspace.github_operations.issues.cache._load_cache_file")
    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    def test_api_failure_returns_stale_cached_issues(
        self,
        mock_get_path: Mock,
        mock_load: Mock,
        mock_now: Mock,
        mock_save: Mock,
        mock_cache_issue_manager: Mock,
        tmp_path: Path,
    ) -> None:
        """API failure should return all stale cached issues."""
        cache_data: CacheData = {
            "last_checked": "2025-12-31T10:00:00Z",
            "issues": {
                "1": self._make_issue(1, "Issue one"),
                "2": self._make_issue(2, "Issue two"),
                "3": self._make_issue(3, "Issue three"),
            },
        }
        mock_get_path.return_value = tmp_path / "cache.json"
        mock_load.return_value = cache_data
        mock_now.return_value = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)

        mock_cache_issue_manager._list_issues_no_error_handling.side_effect = (
            ConnectionError("Network failure")
        )

        result = get_all_cached_issues(
            RepoIdentifier.from_full_name("test/repo"),
            mock_cache_issue_manager,
            force_refresh=True,
        )

        assert len(result) == 3
        returned_numbers = {issue["number"] for issue in result}
        assert returned_numbers == {1, 2, 3}

    @patch(
        "mcp_workspace.github_operations.issues.cache._save_cache_file",
        return_value=True,
    )
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    @patch("mcp_workspace.github_operations.issues.cache._load_cache_file")
    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    def test_api_failure_restores_snapshot_on_full_refresh(
        self,
        mock_get_path: Mock,
        mock_load: Mock,
        mock_now: Mock,
        mock_save: Mock,
        mock_cache_issue_manager: Mock,
        tmp_path: Path,
    ) -> None:
        """Full refresh clears issues before API call; snapshot must restore them on failure."""
        cache_data: CacheData = {
            "last_checked": None,  # Triggers full refresh
            "issues": {
                "10": self._make_issue(10, "Cached issue A"),
                "20": self._make_issue(20, "Cached issue B"),
            },
        }
        mock_get_path.return_value = tmp_path / "cache.json"
        mock_load.return_value = cache_data
        mock_now.return_value = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)

        # _fetch_and_merge_issues will clear cache_data["issues"] = {} on full refresh
        # THEN call the API which raises — snapshot must restore the original issues
        mock_cache_issue_manager._list_issues_no_error_handling.side_effect = (
            RuntimeError("API unavailable")
        )

        result = get_all_cached_issues(
            RepoIdentifier.from_full_name("test/repo"), mock_cache_issue_manager
        )

        # Despite full refresh clearing cache, snapshot should restore original issues
        assert len(result) == 2
        returned_numbers = {issue["number"] for issue in result}
        assert returned_numbers == {10, 20}

    @patch(
        "mcp_workspace.github_operations.issues.cache._save_cache_file",
        return_value=True,
    )
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    @patch("mcp_workspace.github_operations.issues.cache._load_cache_file")
    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    def test_repo_lookup_failure_does_not_advance_last_checked(
        self,
        mock_get_path: Mock,
        mock_load: Mock,
        mock_now: Mock,
        mock_save: Mock,
        mock_cache_issue_manager: Mock,
        tmp_path: Path,
    ) -> None:
        """Repo lookup failure (RuntimeError from _list_issues_no_error_handling
        when _get_repository() returns None) must be treated the same as any
        other API failure: stale cache returned, last_checked not advanced."""
        original_last_checked = "2025-12-31T10:00:00Z"
        cache_data: CacheData = {
            "last_checked": original_last_checked,
            "issues": {
                "1": self._make_issue(1),
            },
        }
        mock_get_path.return_value = tmp_path / "cache.json"
        mock_load.return_value = cache_data
        mock_now.return_value = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)

        # Simulate the exact failure raised by _list_issues_no_error_handling
        # when _get_repository() returns None.
        mock_cache_issue_manager._list_issues_no_error_handling.side_effect = (
            RuntimeError("Failed to get repository")
        )

        result = get_all_cached_issues(
            RepoIdentifier.from_full_name("test/repo"),
            mock_cache_issue_manager,
            force_refresh=True,
        )

        # last_checked must NOT have been advanced (no save)
        mock_save.assert_not_called()
        # Stale cache issue should still be returned
        assert len(result) == 1
        assert result[0]["number"] == 1

    @patch(
        "mcp_workspace.github_operations.issues.cache._save_cache_file",
        return_value=True,
    )
    @patch("mcp_workspace.github_operations.issues.cache.now_utc")
    @patch("mcp_workspace.github_operations.issues.cache._load_cache_file")
    @patch("mcp_workspace.github_operations.issues.cache._get_cache_file_path")
    def test_successful_fetch_still_advances_last_checked(
        self,
        mock_get_path: Mock,
        mock_load: Mock,
        mock_now: Mock,
        mock_save: Mock,
        mock_cache_issue_manager: Mock,
        tmp_path: Path,
    ) -> None:
        """Successful fetch should advance last_checked and save cache."""
        original_last_checked = "2025-12-31T10:00:00Z"
        cache_data: CacheData = {
            "last_checked": original_last_checked,
            "issues": {"1": self._make_issue(1)},
        }
        mock_get_path.return_value = tmp_path / "cache.json"
        mock_load.return_value = cache_data
        now_time = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = now_time

        new_issue = self._make_issue(2, "New issue")
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = [
            new_issue
        ]

        result = get_all_cached_issues(
            RepoIdentifier.from_full_name("test/repo"),
            mock_cache_issue_manager,
            force_refresh=True,
        )

        # Cache should be saved with updated last_checked
        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][1]
        assert saved_data["last_checked"] != original_last_checked
        # New issue should be in results
        returned_numbers = {issue["number"] for issue in result}
        assert 2 in returned_numbers


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
