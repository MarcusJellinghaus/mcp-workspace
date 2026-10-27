"""Tests for issue cache functionality — additional issue fetch rule and saving.

Split from test_cache_additional.py: when additional (session) issues are
fetched individually, and how fetched issues are saved on early-return paths.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

from mcp_workspace.github_operations.issues import CacheData, IssueData
from mcp_workspace.github_operations.issues._cache_io import _save_cache_file
from mcp_workspace.github_operations.issues.cache import (
    CACHE_SCHEMA_VERSION,
    get_all_cached_issues,
)
from mcp_workspace.utils.repo_identifier import RepoIdentifier

_NOW = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
_NOW_STR = "2025-12-31T12:00:00+00:00"
_FRESH_STAMP = "2025-12-31T11:00:00+00:00"  # 1 hour old, < 1440 min
_STALE_STAMP = "2025-12-29T12:00:00+00:00"  # 2 days old, > 1440 min


def _issue(number: int, state: str = "open", title: str = "Issue") -> IssueData:
    """Create a minimal IssueData for testing."""
    return IssueData(
        number=number,
        state=state,
        labels=["bug"],
        updated_at="2025-12-31T09:00:00Z",
        url=f"https://github.com/owner/repo/issues/{number}",
        title=title,
        body="body",
        assignees=[],
        user="testuser",
        created_at="2025-12-31T08:00:00Z",
        locked=False,
        author_association="OWNER",
    )


class TestAdditionalIssuesFetchRule:
    """Tests for when additional issues are fetched individually."""

    def _write_cache(
        self,
        cache_file: Path,
        issues: Dict[str, IssueData],
        cached_at: Dict[str, str],
    ) -> None:
        """Write a cache that triggers an incremental refresh at _NOW."""
        cache_data: CacheData = {
            "last_checked": "2025-12-31T11:58:00+00:00",  # outside 50s protection
            "last_full_refresh": "2025-12-31T11:00:00+00:00",
            "updates_covered_through": "2025-12-31T11:00:00+00:00",
            "cached_at": cached_at,
            "version": CACHE_SCHEMA_VERSION,
            "issues": issues,
        }
        _save_cache_file(cache_file, cache_data)

    def _run(
        self,
        cache_file: Path,
        manager: Mock,
        additional_issues: List[int],
        force_refresh: bool = False,
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
                force_refresh=force_refresh,
                additional_issues=additional_issues,
            )

    def _saved(self, cache_file: Path) -> Dict[str, Any]:
        with cache_file.open("r") as f:
            data: Dict[str, Any] = json.load(f)
        return data

    def test_fresh_cached_issue_not_fetched(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """Cached with fresh cached_at → get_issue not called, cached issue returned."""
        cache_file = tmp_path / "cache.json"
        cached = _issue(123, "closed", "Cached")
        self._write_cache(cache_file, {"123": cached}, {"123": _FRESH_STAMP})

        result = self._run(cache_file, mock_cache_issue_manager, [123])

        mock_cache_issue_manager.get_issue.assert_not_called()
        assert result == [cached]

    def test_stale_cached_issue_fetched_and_restamped(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """Cached with cached_at older than cache_refresh_minutes → fetched, re-stamped."""
        cache_file = tmp_path / "cache.json"
        self._write_cache(
            cache_file, {"123": _issue(123, "open", "Cached")}, {"123": _STALE_STAMP}
        )
        mock_cache_issue_manager.get_issue.return_value = _issue(
            123, "closed", "Fetched"
        )

        result = self._run(cache_file, mock_cache_issue_manager, [123])

        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
        assert [i["title"] for i in result] == ["Fetched"]
        saved = self._saved(cache_file)
        assert saved["issues"]["123"]["state"] == "closed"
        assert saved["cached_at"]["123"] == _NOW_STR

    def test_missing_cached_at_fetched(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """Cached with missing cached_at → fetched."""
        cache_file = tmp_path / "cache.json"
        self._write_cache(cache_file, {"123": _issue(123, title="Cached")}, {})
        mock_cache_issue_manager.get_issue.return_value = _issue(123, title="Fetched")

        result = self._run(cache_file, mock_cache_issue_manager, [123])

        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
        assert [i["title"] for i in result] == ["Fetched"]
        assert self._saved(cache_file)["cached_at"]["123"] == _NOW_STR

    def test_unparseable_cached_at_fetched(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """Cached with unparseable cached_at → fetched."""
        cache_file = tmp_path / "cache.json"
        self._write_cache(
            cache_file, {"123": _issue(123, title="Cached")}, {"123": "not-a-date"}
        )
        mock_cache_issue_manager.get_issue.return_value = _issue(123, title="Fetched")

        result = self._run(cache_file, mock_cache_issue_manager, [123])

        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
        assert [i["title"] for i in result] == ["Fetched"]
        assert self._saved(cache_file)["cached_at"]["123"] == _NOW_STR

    def test_force_refresh_fetches_fresh_cached_issue(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """force_refresh bypasses a fresh cached_at; fetched version kept and stamped."""
        cache_file = tmp_path / "cache.json"
        self._write_cache(
            cache_file,
            {"123": _issue(123, "closed", "Cached")},
            {"123": _FRESH_STAMP},
        )
        mock_cache_issue_manager.get_issue.return_value = _issue(
            123, "closed", "Fetched"
        )

        result = self._run(
            cache_file, mock_cache_issue_manager, [123], force_refresh=True
        )

        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
        assert [i["title"] for i in result] == ["Fetched"]
        saved = self._saved(cache_file)
        assert saved["issues"]["123"]["title"] == "Fetched"
        assert saved["cached_at"]["123"] == _NOW_STR

    def test_empty_issue_not_cached_and_fetched_again(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """get_issue returning number == 0 → not cached, fetched again next call."""
        cache_file = tmp_path / "cache.json"
        self._write_cache(cache_file, {}, {})
        mock_cache_issue_manager.get_issue.return_value = _issue(0)

        self._run(cache_file, mock_cache_issue_manager, [404])
        saved = self._saved(cache_file)
        assert "404" not in saved["issues"]
        assert "404" not in saved["cached_at"]

        result = self._run(cache_file, mock_cache_issue_manager, [404])

        assert mock_cache_issue_manager.get_issue.call_count == 2
        assert result == []

    def test_failed_fetch_keeps_cached_copy_and_stamp(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """get_issue raises for a stale cached issue → cached copy kept, stamp unchanged."""
        cache_file = tmp_path / "cache.json"
        cached = _issue(123, "open", "Cached")
        self._write_cache(cache_file, {"123": cached}, {"123": _STALE_STAMP})
        mock_cache_issue_manager.get_issue.side_effect = Exception("API Error")

        result = self._run(cache_file, mock_cache_issue_manager, [123])

        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
        assert result == [cached]
        saved = self._saved(cache_file)
        assert saved["issues"]["123"] == cached
        assert saved["cached_at"]["123"] == _STALE_STAMP

    def test_fresh_open_session_issues_cost_zero_fetches(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """Acceptance: N fresh cached open session issues → zero get_issue calls."""
        cache_file = tmp_path / "cache.json"
        numbers = [101, 102, 103, 104, 105]
        self._write_cache(
            cache_file,
            {str(n): _issue(n) for n in numbers},
            {str(n): _FRESH_STAMP for n in numbers},
        )

        result = self._run(cache_file, mock_cache_issue_manager, numbers)

        mock_cache_issue_manager.get_issue.assert_not_called()
        assert sorted(i["number"] for i in result) == numbers


_PROTECTED_LAST_CHECKED = "2025-12-31T11:59:30+00:00"  # 30s ago, inside 50s window
_OUTSIDE_LAST_CHECKED = "2025-12-31T11:58:00+00:00"  # outside 50s window
_LAST_FULL_REFRESH = "2025-12-31T11:00:00+00:00"
_COVERED_THROUGH = "2025-12-31T11:00:00+00:00"


class TestSaveFetchedIssuesOnEarlyReturn:
    """Fetched additional issues are saved on duplicate-protection and list-failure paths."""

    def _cache(
        self,
        last_checked: str,
        issues: Optional[Dict[str, IssueData]] = None,
        cached_at: Optional[Dict[str, str]] = None,
    ) -> CacheData:
        return {
            "last_checked": last_checked,
            "last_full_refresh": _LAST_FULL_REFRESH,
            "updates_covered_through": _COVERED_THROUGH,
            "cached_at": cached_at or {},
            "version": CACHE_SCHEMA_VERSION,
            "issues": issues or {},
        }

    def _run(
        self, cache_file: Path, manager: Mock, additional_issues: List[int]
    ) -> List[IssueData]:
        """Call get_all_cached_issues against a real cache_file at _NOW."""
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

    def _saved(self, cache_file: Path) -> Dict[str, Any]:
        with cache_file.open("r") as f:
            data: Dict[str, Any] = json.load(f)
        return data

    def test_uncached_issue_saved_with_timestamps_untouched(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """Duplicate protection: uncached issue fetched once, saved, timestamps kept."""
        snapshots = [
            self._cache(_PROTECTED_LAST_CHECKED),
            self._cache(_PROTECTED_LAST_CHECKED),
        ]
        mock_cache_issue_manager.get_issue.return_value = _issue(123, "closed")

        with (
            patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path",
                return_value=tmp_path / "cache.json",
            ),
            patch(
                "mcp_workspace.github_operations.issues.cache._load_cache_file",
                side_effect=snapshots,
            ),
            patch(
                "mcp_workspace.github_operations.issues.cache._save_cache_file",
                return_value=True,
            ) as mock_save,
            patch(
                "mcp_workspace.github_operations.issues.cache.now_utc",
                return_value=_NOW,
            ),
        ):
            result = get_all_cached_issues(
                RepoIdentifier.from_full_name("owner/repo"),
                mock_cache_issue_manager,
                additional_issues=[123],
            )

        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
        mock_cache_issue_manager._list_issues_no_error_handling.assert_not_called()
        assert [i["number"] for i in result] == [123]
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][1]
        assert saved["last_checked"] == _PROTECTED_LAST_CHECKED
        assert saved["updates_covered_through"] == _COVERED_THROUGH
        assert saved["last_full_refresh"] == _LAST_FULL_REFRESH
        assert saved["cached_at"]["123"] == _NOW_STR
        assert saved["issues"]["123"]["state"] == "closed"

    def test_reload_merges_into_newer_on_disk_cache(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """Save reloads the file: another process's issues and timestamps survive."""
        newer_last_checked = "2025-12-31T11:59:45+00:00"
        first = self._cache(_PROTECTED_LAST_CHECKED)
        second = self._cache(
            newer_last_checked,
            issues={"200": _issue(200)},
            cached_at={"200": _FRESH_STAMP},
        )
        mock_cache_issue_manager.get_issue.return_value = _issue(123, "closed")

        with (
            patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path",
                return_value=tmp_path / "cache.json",
            ),
            patch(
                "mcp_workspace.github_operations.issues.cache._load_cache_file",
                side_effect=[first, second],
            ),
            patch(
                "mcp_workspace.github_operations.issues.cache._save_cache_file",
                return_value=True,
            ) as mock_save,
            patch(
                "mcp_workspace.github_operations.issues.cache.now_utc",
                return_value=_NOW,
            ),
        ):
            get_all_cached_issues(
                RepoIdentifier.from_full_name("owner/repo"),
                mock_cache_issue_manager,
                additional_issues=[123],
            )

        mock_save.assert_called_once()
        saved = mock_save.call_args[0][1]
        assert set(saved["issues"]) == {"123", "200"}
        assert saved["cached_at"] == {"200": _FRESH_STAMP, "123": _NOW_STR}
        assert saved["last_checked"] == newer_last_checked
        assert saved["updates_covered_through"] == _COVERED_THROUGH
        assert saved["last_full_refresh"] == _LAST_FULL_REFRESH

    def test_nothing_fetched_no_save(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """All additional issues cached and fresh → nothing saved."""
        cached = self._cache(
            _PROTECTED_LAST_CHECKED,
            issues={"123": _issue(123, "closed")},
            cached_at={"123": _FRESH_STAMP},
        )

        with (
            patch(
                "mcp_workspace.github_operations.issues.cache._get_cache_file_path",
                return_value=tmp_path / "cache.json",
            ),
            patch(
                "mcp_workspace.github_operations.issues.cache._load_cache_file",
                return_value=cached,
            ),
            patch(
                "mcp_workspace.github_operations.issues.cache._save_cache_file",
                return_value=True,
            ) as mock_save,
            patch(
                "mcp_workspace.github_operations.issues.cache.now_utc",
                return_value=_NOW,
            ),
        ):
            get_all_cached_issues(
                RepoIdentifier.from_full_name("owner/repo"),
                mock_cache_issue_manager,
                additional_issues=[123],
            )

        mock_cache_issue_manager.get_issue.assert_not_called()
        mock_save.assert_not_called()

    def test_second_call_after_save_does_not_refetch(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """Duplicate protection with a real cache file: second call costs no fetch."""
        cache_file = tmp_path / "cache.json"
        _save_cache_file(cache_file, self._cache(_PROTECTED_LAST_CHECKED))
        mock_cache_issue_manager.get_issue.return_value = _issue(123, "closed")

        self._run(cache_file, mock_cache_issue_manager, [123])
        result = self._run(cache_file, mock_cache_issue_manager, [123])

        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
        assert [i["number"] for i in result] == [123]
        assert self._saved(cache_file)["last_checked"] == _PROTECTED_LAST_CHECKED

    def test_list_outage_saves_fetched_issue_once(
        self, mock_cache_issue_manager: Mock, tmp_path: Path
    ) -> None:
        """List API down: stale session issue fetched once, saved, timestamps kept."""
        cache_file = tmp_path / "cache.json"
        _save_cache_file(
            cache_file,
            self._cache(
                _OUTSIDE_LAST_CHECKED,
                issues={"100": _issue(100), "123": _issue(123, "open", "Cached")},
                cached_at={"100": _FRESH_STAMP, "123": _STALE_STAMP},
            ),
        )
        mock_cache_issue_manager._list_issues_no_error_handling.side_effect = (
            ConnectionError("Network failure")
        )
        mock_cache_issue_manager.get_issue.return_value = _issue(
            123, "closed", "Fetched"
        )

        result = self._run(cache_file, mock_cache_issue_manager, [123])

        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
        assert {i["number"]: i["title"] for i in result} == {
            100: "Issue",
            123: "Fetched",
        }
        saved = self._saved(cache_file)
        assert saved["last_checked"] == _OUTSIDE_LAST_CHECKED
        assert saved["updates_covered_through"] == _COVERED_THROUGH
        assert saved["last_full_refresh"] == _LAST_FULL_REFRESH
        assert saved["issues"]["123"]["state"] == "closed"
        assert saved["cached_at"] == {"100": _FRESH_STAMP, "123": _NOW_STR}

        self._run(cache_file, mock_cache_issue_manager, [123])

        mock_cache_issue_manager.get_issue.assert_called_once_with(123)
