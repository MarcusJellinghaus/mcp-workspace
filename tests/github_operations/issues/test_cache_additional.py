"""Tests for issue cache functionality — additional_issues and API failures.

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
