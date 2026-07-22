"""Unit tests for IssueBranchManager PR/branch resolution helper methods."""

# pylint: disable=protected-access  # Tests need to access protected members for mocking

from typing import Any
from unittest.mock import Mock, patch

from mcp_workspace.github_operations.issues import IssueBranchManager


class TestExtractPrsByStates:
    """Test suite for IssueBranchManager._extract_prs_by_states()."""

    @staticmethod
    def _make_pr_node(
        number: int, state: str, head_ref: str, is_draft: bool = False
    ) -> dict[str, Any]:
        """Helper to build a CrossReferencedEvent timeline node."""
        return {
            "__typename": "CrossReferencedEvent",
            "source": {
                "number": number,
                "state": state,
                "isDraft": is_draft,
                "headRefName": head_ref,
            },
        }

    def test_extract_prs_by_states_open_only(self) -> None:
        """Filters OPEN PRs, excludes CLOSED and MERGED."""
        timeline_items = [
            self._make_pr_node(1, "OPEN", "branch-open"),
            self._make_pr_node(2, "CLOSED", "branch-closed"),
            self._make_pr_node(3, "MERGED", "branch-merged"),
            self._make_pr_node(4, "OPEN", "branch-open-2", is_draft=True),
        ]

        result = IssueBranchManager._extract_prs_by_states(timeline_items, {"OPEN"})

        assert len(result) == 2
        assert result[0]["headRefName"] == "branch-open"
        assert result[1]["headRefName"] == "branch-open-2"

    def test_extract_prs_by_states_closed_only(self) -> None:
        """Filters CLOSED PRs, excludes OPEN and MERGED."""
        timeline_items = [
            self._make_pr_node(1, "OPEN", "branch-open"),
            self._make_pr_node(2, "CLOSED", "branch-closed"),
            self._make_pr_node(3, "MERGED", "branch-merged"),
            self._make_pr_node(4, "CLOSED", "branch-closed-2"),
        ]

        result = IssueBranchManager._extract_prs_by_states(timeline_items, {"CLOSED"})

        assert len(result) == 2
        assert result[0]["headRefName"] == "branch-closed"
        assert result[1]["headRefName"] == "branch-closed-2"

    def test_extract_prs_by_states_multiple_states(self) -> None:
        """Passing {"OPEN", "CLOSED"} returns both OPEN and CLOSED, excludes MERGED."""
        timeline_items = [
            self._make_pr_node(1, "OPEN", "branch-open"),
            self._make_pr_node(2, "CLOSED", "branch-closed"),
            self._make_pr_node(3, "MERGED", "branch-merged"),
        ]

        result = IssueBranchManager._extract_prs_by_states(
            timeline_items, {"OPEN", "CLOSED"}
        )

        assert len(result) == 2
        head_refs = {pr["headRefName"] for pr in result}
        assert head_refs == {"branch-open", "branch-closed"}

    def test_extract_prs_by_states_skips_non_cross_referenced(self) -> None:
        """Skips nodes that are not CrossReferencedEvent."""
        timeline_items: list[dict[str, Any]] = [
            {
                "__typename": "SomeOtherEvent",
                "source": {"state": "OPEN", "headRefName": "x"},
            },
            self._make_pr_node(1, "OPEN", "branch-open"),
        ]

        result = IssueBranchManager._extract_prs_by_states(timeline_items, {"OPEN"})

        assert len(result) == 1
        assert result[0]["headRefName"] == "branch-open"

    def test_extract_prs_by_states_skips_missing_fields(self) -> None:
        """Skips nodes missing state or headRefName."""
        timeline_items = [
            {
                "__typename": "CrossReferencedEvent",
                "source": {"number": 1, "title": "Issue, not PR"},
            },
            self._make_pr_node(2, "OPEN", "branch-open"),
        ]

        result = IssueBranchManager._extract_prs_by_states(timeline_items, {"OPEN"})

        assert len(result) == 1
        assert result[0]["headRefName"] == "branch-open"

    def test_extract_prs_by_states_empty_input(self) -> None:
        """Returns empty list for empty timeline items."""
        result = IssueBranchManager._extract_prs_by_states([], {"OPEN"})
        assert result == []


def _make_git_ref(ref_name: str) -> Mock:
    """Helper to build a mock GitRef object."""
    ref = Mock()
    ref.ref = ref_name
    return ref


class TestSearchBranchesByPattern:
    """Test suite for IssueBranchManager._search_branches_by_pattern()."""

    def test_search_branches_no_match(self, mock_manager: IssueBranchManager) -> None:
        """Empty refs list returns None."""
        mock_repo = Mock()
        # Both prefix pass and full scan return empty
        mock_repo.get_git_matching_refs.side_effect = [
            [],  # prefix pass
            [],  # full scan
        ]

        result = mock_manager._search_branches_by_pattern(252, mock_repo)

        assert result is None

    def test_search_branches_single_match_prefix(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Prefix pass finds '252-bar' — returns branch name without full scan."""
        mock_repo = Mock()
        # Prefix pass returns a matching ref
        mock_repo.get_git_matching_refs.return_value = [
            _make_git_ref("refs/heads/252-bar"),
        ]

        result = mock_manager._search_branches_by_pattern(252, mock_repo)

        assert result == "252-bar"
        # Should only call get_git_matching_refs once (prefix pass)
        mock_repo.get_git_matching_refs.assert_called_once_with("heads/252")

    def test_search_branches_single_match_nested(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Prefix pass empty, full scan finds 'feature/252-foo' — returns branch."""
        mock_repo = Mock()
        # Prefix pass returns no matches, full scan returns nested match
        mock_repo.get_git_matching_refs.side_effect = [
            [],  # prefix pass
            [_make_git_ref("refs/heads/feature/252-foo")],  # full scan
        ]

        result = mock_manager._search_branches_by_pattern(252, mock_repo)

        assert result == "feature/252-foo"
        assert mock_repo.get_git_matching_refs.call_count == 2

    def test_search_branches_multiple_matches(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Two matching refs in prefix pass returns None (ambiguous)."""
        mock_repo = Mock()
        mock_repo.get_git_matching_refs.return_value = [
            _make_git_ref("refs/heads/252-bar"),
            _make_git_ref("refs/heads/252-baz"),
        ]

        result = mock_manager._search_branches_by_pattern(252, mock_repo)

        assert result is None

    def test_search_branches_500_cap(self, mock_manager: IssueBranchManager) -> None:
        """501 refs in full scan — processes first 500, logs warning."""
        mock_repo = Mock()
        # Prefix pass: no matches
        # Full scan: 501 refs, none matching the pattern
        refs_501 = [_make_git_ref(f"refs/heads/other-branch-{i}") for i in range(501)]
        mock_repo.get_git_matching_refs.side_effect = [
            [],  # prefix pass
            refs_501,  # full scan
        ]

        with patch(
            "mcp_workspace.github_operations.issues.branch_manager.logger"
        ) as mock_logger:
            result = mock_manager._search_branches_by_pattern(252, mock_repo)

        assert result is None
        # Should log warning about exceeding 500 refs
        mock_logger.warning.assert_called()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "500" in warning_msg

    def test_search_branches_pattern_variations(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """Matches expected patterns, does NOT match false positives."""
        mock_repo = Mock()

        # Test matching patterns individually via full scan
        # Test: "feature/252-foo" should match
        mock_repo.get_git_matching_refs.side_effect = [
            [],  # prefix pass
            [_make_git_ref("refs/heads/feature/252-foo")],  # full scan
        ]
        assert (
            mock_manager._search_branches_by_pattern(252, mock_repo)
            == "feature/252-foo"
        )

        # Test: "252-bar" should match (via prefix pass)
        mock_repo.get_git_matching_refs.side_effect = [
            [_make_git_ref("refs/heads/252-bar")],  # prefix pass
        ]
        assert mock_manager._search_branches_by_pattern(252, mock_repo) == "252-bar"

        # Test: "fix/252_baz" should match (underscore separator)
        mock_repo.get_git_matching_refs.side_effect = [
            [],  # prefix pass
            [_make_git_ref("refs/heads/fix/252_baz")],  # full scan
        ]
        assert mock_manager._search_branches_by_pattern(252, mock_repo) == "fix/252_baz"

        # Test: "1252-foo" should NOT match (different number)
        mock_repo.get_git_matching_refs.side_effect = [
            [_make_git_ref("refs/heads/1252-foo")],  # prefix pass
            [],  # full scan
        ]
        assert mock_manager._search_branches_by_pattern(252, mock_repo) is None

        # Test: "252" alone (no separator) should NOT match
        mock_repo.get_git_matching_refs.side_effect = [
            [_make_git_ref("refs/heads/252")],  # prefix pass
            [],  # full scan
        ]
        assert mock_manager._search_branches_by_pattern(252, mock_repo) is None
