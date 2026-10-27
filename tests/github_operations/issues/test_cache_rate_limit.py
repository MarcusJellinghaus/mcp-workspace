"""Tests for issue cache rate-limit handling: raise, and save nothing."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import Mock, patch

import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations import GitHubRateLimitError
from mcp_workspace.github_operations.issues import CacheData, IssueData
from mcp_workspace.github_operations.issues._cache_io import _save_cache_file
from mcp_workspace.github_operations.issues.cache import (
    CACHE_SCHEMA_VERSION,
    get_all_cached_issues,
)
from mcp_workspace.utils.repo_identifier import RepoIdentifier

_NOW = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
_PROTECTED_LAST_CHECKED = "2025-12-31T11:59:30+00:00"  # 30s ago, inside 50s window
_OUTSIDE_LAST_CHECKED = "2025-12-31T11:58:00+00:00"  # outside 50s window
_LAST_FULL_REFRESH = "2025-12-31T11:00:00+00:00"
_COVERED_THROUGH = "2025-12-31T11:00:00+00:00"
_FRESH_STAMP = "2025-12-31T11:00:00+00:00"


def _issue(number: int, state: str = "open") -> IssueData:
    """Create a minimal IssueData for testing."""
    return IssueData(
        number=number,
        state=state,
        labels=["bug"],
        updated_at="2025-12-31T09:00:00Z",
        url=f"https://github.com/owner/repo/issues/{number}",
        title="Issue",
        body="body",
        assignees=[],
        user="testuser",
        created_at="2025-12-31T08:00:00Z",
        locked=False,
        author_association="OWNER",
    )


def _rate_limit() -> GithubException:
    return GithubException(
        403, {"message": "API rate limit exceeded"}, {"X-RateLimit-Remaining": "0"}
    )


def _write_cache(
    cache_file: Path, last_checked: str, issues: Optional[Dict[str, IssueData]] = None
) -> None:
    issues = issues or {}
    cache_data: CacheData = {
        "last_checked": last_checked,
        "last_full_refresh": _LAST_FULL_REFRESH,
        "updates_covered_through": _COVERED_THROUGH,
        "cached_at": {key: _FRESH_STAMP for key in issues},
        "version": CACHE_SCHEMA_VERSION,
        "issues": issues,
    }
    _save_cache_file(cache_file, cache_data)


def _run(
    cache_file: Path, manager: Mock, additional_issues: Optional[List[int]] = None
) -> List[IssueData]:
    """Call get_all_cached_issues against cache_file at _NOW."""
    with (
        patch(
            "mcp_workspace.github_operations.issues.cache._get_cache_file_path",
            return_value=cache_file,
        ),
        patch(
            "mcp_workspace.github_operations.issues.cache.now_utc",
            return_value=_NOW,
        ),
    ):
        return get_all_cached_issues(
            RepoIdentifier.from_full_name("owner/repo"),
            manager,
            additional_issues=additional_issues,
        )


_SAVE_TARGET = "mcp_workspace.github_operations.issues.cache._save_cache_file"


class TestIssueCacheRateLimit:
    """A rate limit raises GitHubRateLimitError and nothing is written."""

    def test_incremental_list_rate_limit_raises_without_save(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """Even an additional issue fetched before the list failure is not saved."""
        cache_file = tmp_path / "cache.json"
        _write_cache(cache_file, _OUTSIDE_LAST_CHECKED, {"1": _issue(1)})
        original = _rate_limit()
        mock_cache_issue_manager._list_issues_no_error_handling.side_effect = original
        mock_cache_issue_manager.get_issue.return_value = _issue(123, "closed")

        with (
            patch(_SAVE_TARGET) as mock_save,
            pytest.raises(GitHubRateLimitError) as info,
        ):
            _run(cache_file, mock_cache_issue_manager, additional_issues=[123])

        assert info.value.__cause__ is original
        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
        mock_save.assert_not_called()

    @pytest.mark.parametrize(
        "last_checked", [_OUTSIDE_LAST_CHECKED, _PROTECTED_LAST_CHECKED]
    )
    def test_additional_issue_rate_limit_raises_without_save(
        self, mock_cache_issue_manager: Mock, tmp_path: Path, last_checked: str
    ) -> None:
        """Normal and duplicate-protection paths: no save after the raise."""
        cache_file = tmp_path / "cache.json"
        _write_cache(cache_file, last_checked)
        mock_cache_issue_manager.get_issue.side_effect = [
            _issue(122, "closed"),
            _rate_limit(),
        ]

        with (
            patch(_SAVE_TARGET) as mock_save,
            pytest.raises(GitHubRateLimitError),
        ):
            _run(cache_file, mock_cache_issue_manager, additional_issues=[122, 123])

        mock_save.assert_not_called()
        mock_cache_issue_manager._list_issues_no_error_handling.assert_not_called()

    def test_put_back_rate_limit_raises_without_save(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """A rate limit while re-checking a cleared session issue is not swallowed."""
        cache_file = tmp_path / "cache.json"
        cache_data: CacheData = {
            "last_checked": _OUTSIDE_LAST_CHECKED,
            "last_full_refresh": "2025-12-01T00:00:00+00:00",  # full refresh due
            "updates_covered_through": _COVERED_THROUGH,
            "cached_at": {"5": _FRESH_STAMP},
            "version": CACHE_SCHEMA_VERSION,
            "issues": {"5": _issue(5)},
        }
        _save_cache_file(cache_file, cache_data)
        mock_cache_issue_manager._list_issues_no_error_handling.return_value = []
        original = _rate_limit()
        mock_cache_issue_manager.get_issue.side_effect = original

        with (
            patch(_SAVE_TARGET) as mock_save,
            pytest.raises(GitHubRateLimitError) as info,
        ):
            _run(cache_file, mock_cache_issue_manager, additional_issues=[5])

        assert info.value.__cause__ is original
        mock_cache_issue_manager.get_issue.assert_called_once_with(5)
        mock_save.assert_not_called()

    def test_non_rate_limit_error_returns_stale(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        cache_file = tmp_path / "cache.json"
        _write_cache(cache_file, _OUTSIDE_LAST_CHECKED, {"1": _issue(1)})
        mock_cache_issue_manager._list_issues_no_error_handling.side_effect = (
            GithubException(500, {"message": "Server Error"}, {})
        )

        with patch(_SAVE_TARGET) as mock_save:
            result = _run(cache_file, mock_cache_issue_manager)

        assert [i["number"] for i in result] == [1]
        mock_save.assert_not_called()
