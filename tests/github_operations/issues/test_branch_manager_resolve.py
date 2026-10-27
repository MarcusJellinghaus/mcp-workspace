"""Unit tests for IssueBranchManager.resolve_branch_for_issue() (raising core)."""

# pylint: disable=protected-access  # Tests need to access protected members for mocking

from typing import Any
from unittest.mock import Mock, patch

import pytest
from github import GithubException

from mcp_workspace.github_operations.caching.errors import (
    GitHubRateLimitError,
    graphql_rate_limit_error,
)
from mcp_workspace.github_operations.issues import (
    BranchLookup,
    BranchLookupError,
    IssueBranchManager,
)

_RATE_LIMITED_BODY: dict[str, Any] = {
    "data": None,
    "errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}],
}


def _pr_node(number: int, state: str, head: str) -> dict[str, Any]:
    return {
        "__typename": "CrossReferencedEvent",
        "source": {
            "number": number,
            "state": state,
            "isDraft": False,
            "headRefName": head,
        },
    }


def _timeline(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {
        "data": {"repository": {"issue": {"timelineItems": {"nodes": list(nodes)}}}}
    }


def _setup(
    manager: IssueBranchManager,
    linked: list[str] | None = None,
    timeline: Any = None,
) -> Mock:
    """Wire a mock repo, linked branches and a timeline response into manager."""
    mock_repo = Mock()
    mock_repo.owner.login = "test-owner"
    mock_repo.name = "test-repo"
    manager._repository = mock_repo
    manager._fetch_linked_branches = Mock(  # type: ignore[method-assign]
        return_value=[] if linked is None else linked
    )
    manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]
    manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
        return_value=({}, _timeline() if timeline is None else timeline)
    )
    return mock_repo


def _resolve(manager: IssueBranchManager, issue_number: int = 123) -> BranchLookup:
    return manager.resolve_branch_for_issue(issue_number, "test-owner", "test-repo")


class TestResolveBranchForIssue:
    """Test suite for the raising branch-resolution core."""

    def test_found_via_linked_branch(self, mock_manager: IssueBranchManager) -> None:
        """One linked branch is found without querying the timeline."""
        _setup(mock_manager, linked=["123-linked"])

        assert _resolve(mock_manager) == BranchLookup("found", "123-linked")
        mock_manager._github_client._Github__requester.graphql_query.assert_not_called()  # type: ignore[attr-defined]

    def test_ambiguous_linked_branches(self, mock_manager: IssueBranchManager) -> None:
        """Several linked branches are ambiguous."""
        _setup(mock_manager, linked=["123-a", "123-b"])

        assert _resolve(mock_manager) == BranchLookup("ambiguous")

    def test_found_via_open_pr(self, mock_manager: IssueBranchManager) -> None:
        """One open PR is found."""
        _setup(mock_manager, timeline=_timeline(_pr_node(42, "OPEN", "123-open")))

        assert _resolve(mock_manager) == BranchLookup("found", "123-open")

    def test_ambiguous_open_prs(self, mock_manager: IssueBranchManager) -> None:
        """Several open PRs are ambiguous."""
        _setup(
            mock_manager,
            timeline=_timeline(
                _pr_node(42, "OPEN", "123-a"), _pr_node(43, "OPEN", "123-b")
            ),
        )

        assert _resolve(mock_manager) == BranchLookup("ambiguous")

    def test_found_via_closed_pr(self, mock_manager: IssueBranchManager) -> None:
        """A closed PR whose branch still exists is found."""
        mock_repo = _setup(
            mock_manager, timeline=_timeline(_pr_node(50, "CLOSED", "123-closed"))
        )
        mock_repo.get_branch = Mock(return_value=Mock())

        assert _resolve(mock_manager) == BranchLookup("found", "123-closed")

    def test_closed_pr_probe_404_moves_to_next_pr(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """A 404 branch probe skips to the next (older) closed PR."""
        mock_repo = _setup(
            mock_manager,
            timeline=_timeline(
                _pr_node(50, "CLOSED", "123-old"), _pr_node(60, "CLOSED", "123-gone")
            ),
        )
        mock_repo.get_branch = Mock(
            side_effect=[GithubException(404, {"message": "Not found"}, None), Mock()]
        )

        assert _resolve(mock_manager) == BranchLookup("found", "123-old")
        assert [c.args[0] for c in mock_repo.get_branch.call_args_list] == [
            "123-gone",
            "123-old",
        ]

    def test_closed_pr_probe_500_raises(self, mock_manager: IssueBranchManager) -> None:
        """A non-404 branch probe error propagates."""
        mock_repo = _setup(
            mock_manager, timeline=_timeline(_pr_node(50, "CLOSED", "123-closed"))
        )
        mock_repo.get_branch = Mock(
            side_effect=GithubException(500, {"message": "Server Error"}, None)
        )

        with pytest.raises(GithubException) as exc_info:
            _resolve(mock_manager)
        assert exc_info.value.status == 500

    def test_found_via_pattern(self, mock_manager: IssueBranchManager) -> None:
        """Falls through to the pattern lookup and returns its result."""
        mock_repo = _setup(mock_manager)
        mock_manager._pattern_lookup = Mock(  # type: ignore[method-assign]
            return_value=BranchLookup("found", "123-pattern")
        )

        assert _resolve(mock_manager) == BranchLookup("found", "123-pattern")
        mock_manager._pattern_lookup.assert_called_once_with(123, mock_repo)

    def test_ambiguous_pattern(self, mock_manager: IssueBranchManager) -> None:
        """Several pattern matches are ambiguous."""
        mock_repo = _setup(mock_manager)
        mock_repo.get_git_matching_refs = Mock(
            return_value=[
                Mock(ref="refs/heads/123-a"),
                Mock(ref="refs/heads/123-b"),
            ]
        )

        assert _resolve(mock_manager) == BranchLookup("ambiguous")

    def test_not_found(self, mock_manager: IssueBranchManager) -> None:
        """Nothing anywhere is not_found."""
        mock_repo = _setup(mock_manager)
        mock_repo.get_git_matching_refs = Mock(return_value=[])

        assert _resolve(mock_manager) == BranchLookup("not_found")

    @pytest.mark.parametrize("issue_number", [0, -1])
    def test_invalid_issue_number_raises_value_error(
        self, mock_manager: IssueBranchManager, issue_number: int
    ) -> None:
        """An invalid issue number raises ValueError."""
        with pytest.raises(ValueError):
            _resolve(mock_manager, issue_number)

    def test_no_repository_raises(self, mock_manager: IssueBranchManager) -> None:
        """A missing repository raises BranchLookupError."""
        mock_manager._get_repository = Mock(return_value=None)  # type: ignore[method-assign]

        with pytest.raises(BranchLookupError):
            _resolve(mock_manager)

    @pytest.mark.parametrize(
        "timeline",
        [
            {"data": None},
            {"data": {"repository": None}},
            {"data": {"repository": {"issue": None}}},
            # AttributeError while walking the response
            {"data": {"repository": {"issue": {"timelineItems": None}}}},
            # KeyError: open PR without a number
            _timeline(
                {
                    "__typename": "CrossReferencedEvent",
                    "source": {"state": "OPEN", "headRefName": "123-x"},
                }
            ),
        ],
    )
    def test_malformed_timeline_raises(
        self, mock_manager: IssueBranchManager, timeline: dict[str, Any]
    ) -> None:
        """A malformed timeline response raises BranchLookupError."""
        _setup(mock_manager, timeline=timeline)

        with pytest.raises(BranchLookupError):
            _resolve(mock_manager)

    def test_timeline_graphql_exception_propagates(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """A GithubException from the timeline query propagates."""
        _setup(mock_manager)
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            side_effect=GithubException(502, {"message": "Bad Gateway"}, None)
        )

        with pytest.raises(GithubException):
            _resolve(mock_manager)

    def test_timeline_rate_limited_body_raises(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """A RATE_LIMITED timeline body raises GitHubRateLimitError."""
        _setup(mock_manager, timeline=_RATE_LIMITED_BODY)

        with pytest.raises(GitHubRateLimitError):
            _resolve(mock_manager)


class TestLinkedBranchesInCore:
    """The core sees linked-branch failures that get_linked_branches swallows."""

    def _wire_repo(self, manager: IssueBranchManager) -> None:
        mock_repo = Mock()
        mock_repo.owner.login = "test-owner"
        mock_repo.name = "test-repo"
        manager._repository = mock_repo
        manager._github_client._Github__requester = Mock()  # type: ignore[attr-defined]

    def test_query_returning_none_raises(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """_query_linked_branches → None makes _fetch_linked_branches raise."""
        with patch(
            "mcp_workspace.github_operations.issues.branch_manager._query_linked_branches",
            return_value=None,
        ):
            with pytest.raises(BranchLookupError):
                mock_manager._fetch_linked_branches(123)

    def test_query_returning_none_makes_core_raise(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """The core does not continue to the timeline after a failed linked query."""
        self._wire_repo(mock_manager)
        with patch(
            "mcp_workspace.github_operations.issues.branch_manager._query_linked_branches",
            return_value=None,
        ):
            with pytest.raises(BranchLookupError):
                _resolve(mock_manager)
        mock_manager._github_client._Github__requester.graphql_query.assert_not_called()  # type: ignore[attr-defined]

    def test_linked_query_rate_limit_exception_propagates(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """A rate-limit GithubException from the linked query propagates."""
        self._wire_repo(mock_manager)
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            side_effect=GithubException(
                403,
                {"message": "API rate limit exceeded"},
                {"X-RateLimit-Remaining": "0"},
            )
        )

        with pytest.raises(GithubException) as exc_info:
            _resolve(mock_manager)
        assert exc_info.value.status == 403

    def test_linked_query_rate_limited_body_raises(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """A RATE_LIMITED linked-branches body raises GitHubRateLimitError."""
        self._wire_repo(mock_manager)
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, _RATE_LIMITED_BODY)
        )

        with pytest.raises(GitHubRateLimitError):
            _resolve(mock_manager)

    def test_get_linked_branches_rate_limited_body_returns_empty(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """The decorated get_linked_branches keeps returning [] on a RATE_LIMITED body."""
        self._wire_repo(mock_manager)
        mock_manager._github_client._Github__requester.graphql_query = Mock(  # type: ignore[attr-defined]
            return_value=({}, _RATE_LIMITED_BODY)
        )

        assert mock_manager.get_linked_branches(123) == []


class TestGraphqlRateLimitError:
    """Tests for caching.errors.graphql_rate_limit_error."""

    def test_rate_limited_body(self) -> None:
        """A RATE_LIMITED error yields a GitHubRateLimitError."""
        assert isinstance(
            graphql_rate_limit_error(_RATE_LIMITED_BODY), GitHubRateLimitError
        )

    @pytest.mark.parametrize(
        "result",
        [
            {"data": None, "errors": [{"type": "NOT_FOUND"}]},
            {"data": {"repository": None}},
            None,
            "not a dict",
            {"errors": "not a list"},
        ],
    )
    def test_other_bodies(self, result: Any) -> None:
        """Anything but a RATE_LIMITED error yields None."""
        assert graphql_rate_limit_error(result) is None


class TestGetBranchWithPRFallbackWrapper:
    """The decorated wrapper maps core outcomes to Optional[str]."""

    def test_branch_lookup_error_returns_none(
        self, mock_manager: IssueBranchManager
    ) -> None:
        """BranchLookupError from the core returns None."""
        mock_manager.resolve_branch_for_issue = Mock(  # type: ignore[method-assign]
            side_effect=BranchLookupError("boom")
        )

        assert (
            mock_manager.get_branch_with_pr_fallback(123, "test-owner", "test-repo")
            is None
        )

    @pytest.mark.parametrize("issue_number", [0, -1])
    def test_invalid_issue_number_returns_none(
        self, mock_manager: IssueBranchManager, issue_number: int
    ) -> None:
        """An invalid issue number returns None without calling the core."""
        mock_manager.resolve_branch_for_issue = Mock()  # type: ignore[method-assign]

        assert (
            mock_manager.get_branch_with_pr_fallback(
                issue_number, "test-owner", "test-repo"
            )
            is None
        )
        mock_manager.resolve_branch_for_issue.assert_not_called()

    @pytest.mark.parametrize(
        "lookup,expected",
        [
            (BranchLookup("found", "123-x"), "123-x"),
            (BranchLookup("ambiguous"), None),
            (BranchLookup("not_found"), None),
        ],
    )
    def test_lookup_mapped_to_branch(
        self,
        mock_manager: IssueBranchManager,
        lookup: BranchLookup,
        expected: str | None,
    ) -> None:
        """found → branch name; ambiguous / not_found → None."""
        mock_manager.resolve_branch_for_issue = Mock(  # type: ignore[method-assign]
            return_value=lookup
        )

        assert (
            mock_manager.get_branch_with_pr_fallback(123, "test-owner", "test-repo")
            == expected
        )
