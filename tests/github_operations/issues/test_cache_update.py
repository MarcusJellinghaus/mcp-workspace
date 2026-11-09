"""Tests for issue cache functionality — label update and dispatch integration.

Split from the original test_issue_cache.py by whole test class.
"""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_workspace.github_operations.issues import (
    update_issue_labels_in_cache,
)
from mcp_workspace.github_operations.issues.cache_labels import (
    set_issue_labels_in_cache,
)
from mcp_workspace.utils.repo_identifier import RepoIdentifier

_CACHE_LOGGER = "mcp_workspace.github_operations.issues.cache_labels"
_CACHE_PATH_TARGET = f"{_CACHE_LOGGER}._get_cache_file_path"


def _cached_issue(number: int, labels: list[str]) -> dict[str, object]:
    """Build a minimal cached issue entry."""
    return {
        "number": number,
        "state": "open",
        "labels": labels,
        "updated_at": "2025-01-03T09:00:00Z",
        "url": f"https://github.com/test/repo/issues/{number}",
        "title": f"Issue {number}",
        "body": "Body",
        "assignees": [],
        "user": "testuser",
        "created_at": "2025-01-03T08:00:00Z",
        "locked": False,
        "author_association": "OWNER",
    }


class TestSetIssueLabelsInCache:
    """Tests for set_issue_labels_in_cache function."""

    def test_replaces_labels_only(self, tmp_path: Path) -> None:
        """The cached issue's labels are replaced; nothing else changes."""
        cache_path = tmp_path / "test_cache.json"
        other_issue = _cached_issue(456, ["status-05:plan-ready"])
        initial_cache = {
            "last_checked": "2025-01-03T10:30:00Z",
            "issues": {
                "123": _cached_issue(123, ["status-02:awaiting-planning", "bug"]),
                "456": other_issue,
            },
            "cached_at": {"123": "2025-01-03T10:00:00Z"},
        }
        cache_path.write_text(json.dumps(initial_cache))

        with patch(_CACHE_PATH_TARGET, return_value=cache_path):
            set_issue_labels_in_cache(
                RepoIdentifier.from_full_name("test/repo"),
                123,
                ["status-03:planning", "enhancement"],
            )

        updated_cache = json.loads(cache_path.read_text())
        assert updated_cache["issues"]["123"]["labels"] == [
            "status-03:planning",
            "enhancement",
        ]
        assert updated_cache["issues"]["456"] == other_issue
        assert updated_cache["last_checked"] == "2025-01-03T10:30:00Z"
        assert updated_cache["cached_at"] == {"123": "2025-01-03T10:00:00Z"}

    def test_missing_issue_logs_debug_and_does_not_save(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An uncached issue is logged at debug level and the file is untouched."""
        caplog.set_level(logging.DEBUG, logger=_CACHE_LOGGER)
        cache_path = tmp_path / "test_cache.json"
        initial_cache = {
            "last_checked": "2025-01-03T10:30:00Z",
            "issues": {"456": _cached_issue(456, ["bug"])},
        }
        cache_path.write_text(json.dumps(initial_cache))

        with (
            patch(_CACHE_PATH_TARGET, return_value=cache_path),
            patch(f"{_CACHE_LOGGER}._save_cache_file") as mock_save,
        ):
            set_issue_labels_in_cache(
                RepoIdentifier.from_full_name("test/repo"), 123, ["new-label"]
            )

        mock_save.assert_not_called()
        assert json.loads(cache_path.read_text()) == initial_cache
        debug_messages = [
            r.message for r in caplog.records if r.levelno == logging.DEBUG
        ]
        assert any("#123" in msg for msg in debug_messages)
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_failed_save_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """A failed save is logged as a warning and does not raise."""
        caplog.set_level(logging.WARNING, logger=_CACHE_LOGGER)

        with (
            patch(_CACHE_PATH_TARGET, return_value=Path("/fake/cache.json")),
            patch(
                f"{_CACHE_LOGGER}._load_cache_file",
                return_value={
                    "last_checked": None,
                    "issues": {"123": _cached_issue(123, ["old-label"])},
                },
            ),
            patch(f"{_CACHE_LOGGER}._save_cache_file", return_value=False),
        ):
            set_issue_labels_in_cache(
                RepoIdentifier.from_full_name("test/repo"), 123, ["new-label"]
            )

        warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("#123" in msg for msg in warnings)

    def test_load_error_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """An exception while loading is caught and logged as a warning."""
        caplog.set_level(logging.WARNING, logger=_CACHE_LOGGER)

        with (
            patch(_CACHE_PATH_TARGET, return_value=Path("/fake/cache.json")),
            patch(
                f"{_CACHE_LOGGER}._load_cache_file",
                side_effect=Exception("Cache error"),
            ),
        ):
            set_issue_labels_in_cache(
                RepoIdentifier.from_full_name("test/repo"), 123, ["new-label"]
            )

        warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Cache error" in msg for msg in warnings)


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
                        "author_association": "OWNER",
                    }
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            # Mock _get_cache_file_path to return our test path
            with patch(
                "mcp_workspace.github_operations.issues.cache_labels._get_cache_file_path"
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
                        "author_association": "OWNER",
                    }
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            with patch(
                "mcp_workspace.github_operations.issues.cache_labels._get_cache_file_path"
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
                        "author_association": "OWNER",
                    }
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            with patch(
                "mcp_workspace.github_operations.issues.cache_labels._get_cache_file_path"
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
            logging.WARNING,
            logger="mcp_workspace.github_operations.issues.cache_labels",
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
                        "author_association": "OWNER",
                    }
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            with patch(
                "mcp_workspace.github_operations.issues.cache_labels._get_cache_file_path"
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
            logging.WARNING,
            logger="mcp_workspace.github_operations.issues.cache_labels",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.json"

            # Create invalid cache structure
            invalid_cache = {"wrong_structure": "invalid"}
            cache_path.write_text(json.dumps(invalid_cache))

            with patch(
                "mcp_workspace.github_operations.issues.cache_labels._get_cache_file_path"
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
            logging.WARNING,
            logger="mcp_workspace.github_operations.issues.cache_labels",
        )

        with (
            patch(
                "mcp_workspace.github_operations.issues.cache_labels._get_cache_file_path"
            ) as mock_path,
            patch(
                "mcp_workspace.github_operations.issues.cache_labels._load_cache_file"
            ) as mock_load,
            patch(
                "mcp_workspace.github_operations.issues.cache_labels._save_cache_file"
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
                        "author_association": "OWNER",
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
            logging.DEBUG, logger="mcp_workspace.github_operations.issues.cache_labels"
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
                        "author_association": "OWNER",
                    }
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            with patch(
                "mcp_workspace.github_operations.issues.cache_labels._get_cache_file_path"
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
                        "author_association": "OWNER",
                    }
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            # Mock only the cache file path to point to our test cache
            with patch(
                "mcp_workspace.github_operations.issues.cache_labels._get_cache_file_path"
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
                        "author_association": "OWNER",
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
                        "author_association": "OWNER",
                    },
                },
            }
            cache_path.write_text(json.dumps(initial_cache))

            with patch(
                "mcp_workspace.github_operations.issues.cache_labels._get_cache_file_path"
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
            logging.WARNING,
            logger="mcp_workspace.github_operations.issues.cache_labels",
        )

        with (
            patch(
                "mcp_workspace.github_operations.issues.cache_labels._get_cache_file_path"
            ) as mock_path,
            patch(
                "mcp_workspace.github_operations.issues.cache_labels._load_cache_file",
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
