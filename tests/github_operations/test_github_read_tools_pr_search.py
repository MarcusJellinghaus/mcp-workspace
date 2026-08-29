"""Tests for the GitHub PR and search read-only MCP tools in server.py.

The github_search tests here cover result capping and the truncation notice.
Query construction and validation live in ``test_github_search_tool``; the two
modules stay separate because merged they would exceed the file-size limit.
"""

from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.server import github_pr_view, github_search

from ._github_read_tools_helpers import mock_pull as _mock_pull
from .search_helpers import FakeSearchResults, make_search_items

pytestmark = pytest.mark.usefixtures("setup_server")


# =============================================================================
# github_pr_view tests
# =============================================================================


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_pr_view_basic(mock_manager_cls: MagicMock) -> None:
    """Returns formatted text with title, state, branches."""
    mock_repo = MagicMock()
    mock_pr = _mock_pull()
    mock_repo.get_pull.return_value = mock_pr

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo

    result = github_pr_view(number=10)

    assert "#10" in result
    assert "Fix bug" in result
    assert "open" in result
    assert "feature" in result
    assert "main" in result
    mock_repo.get_pull.assert_called_once_with(10)


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_pr_view_with_comments(mock_manager_cls: MagicMock) -> None:
    """Reviews + conversation + inline comments rendered."""
    mock_repo = MagicMock()
    mock_pr = _mock_pull()

    review = MagicMock()
    review.user.login = "reviewer1"
    review.state = "APPROVED"
    review.body = "LGTM"
    mock_pr.get_reviews.return_value = [review]

    conv_comment = MagicMock()
    conv_comment.id = 100
    conv_comment.body = "Nice change"
    conv_comment.user.login = "commenter1"
    conv_comment.created_at.isoformat.return_value = "2024-01-05T00:00:00"
    conv_comment.updated_at = None
    mock_repo.get_issue.return_value.get_comments.return_value = [conv_comment]

    inline_comment = MagicMock()
    inline_comment.path = "src/main.py"
    inline_comment.line = 42
    inline_comment.user.login = "reviewer1"
    inline_comment.body = "nit: rename"
    mock_pr.get_review_comments.return_value = [inline_comment]

    mock_repo.get_pull.return_value = mock_pr
    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo

    result = github_pr_view(number=10, include_comments=True)

    assert "LGTM" in result
    assert "reviewer1" in result
    assert "Nice change" in result
    assert "src/main.py" in result
    assert "nit: rename" in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_pr_view_without_comments(mock_manager_cls: MagicMock) -> None:
    """No comment sections when include_comments=False."""
    mock_repo = MagicMock()
    mock_pr = _mock_pull()
    mock_repo.get_pull.return_value = mock_pr

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo

    result = github_pr_view(number=10, include_comments=False)

    assert "Fix bug" in result
    assert "Reviews" not in result
    assert "Inline" not in result
    mock_pr.get_reviews.assert_not_called()
    mock_pr.get_review_comments.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_pr_view_not_found(mock_manager_cls: MagicMock) -> None:
    """Returns error text on 404."""
    from github.GithubException import UnknownObjectException

    mock_repo = MagicMock()
    mock_repo.get_pull.side_effect = UnknownObjectException(
        404, {"message": "Not Found"}, {}
    )

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo

    result = github_pr_view(number=999)

    assert "Error" in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_pr_view_error(mock_manager_cls: MagicMock) -> None:
    """Returns 'Error: ...' on exception."""
    mock_manager_cls.side_effect = RuntimeError("connection failed")

    result = github_pr_view(number=10)

    assert result == "Error: connection failed"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_pr_view_no_repo(mock_manager_cls: MagicMock) -> None:
    """Returns error when repository not accessible."""
    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = None
    mock_mgr._repo_identifier.api_base_url = "https://gitlab.com/api/v3"

    result = github_pr_view(number=10)

    assert (
        result == "Error: Could not access repository (tried https://gitlab.com/api/v3)"
    )


# =============================================================================
# github_search tests
# =============================================================================


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_max_results_cap(mock_manager_cls: MagicMock) -> None:
    """Results capped at max_results."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults(
        make_search_items(10)
    )

    result = github_search(query="test", max_results=3)

    assert "#1" in result
    assert "#3" in result
    # Item 4+ should not appear in the output lines
    # (only 3 items are passed to the formatter)
    lines = [line for line in result.strip().split("\n") if line.startswith("#")]
    assert len(lines) == 3


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_stops_without_pulling_the_surplus_item(
    mock_manager_cls: MagicMock,
) -> None:
    """islice stops at max_results without pulling item max_results + 1.

    GitHub pages search results at 30, so pulling the surplus item would fetch
    a second page against the 30 requests/minute search rate limit, only to
    discard it. The `enumerate` guard this replaced pulled it before breaking.
    """
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    results = FakeSearchResults(make_search_items(10))

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = results

    github_search(query="test", max_results=3)

    assert results.items_pulled == 3


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_notice_states_exact_total(mock_manager_cls: MagicMock) -> None:
    """The notice reports PaginatedList.totalCount, not the item count."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    results = FakeSearchResults(make_search_items(3), total_count=412)

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = results

    result = github_search(query="test", max_results=3)

    assert "showing 3 of 412 results" in result


@pytest.mark.parametrize("max_results", [0, -1])
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_non_positive_max_results(
    mock_manager_cls: MagicMock, max_results: int
) -> None:
    """A non-positive cap reports suppression, not an empty result set.

    A clamped cap of 0 pulls nothing, so no page is fetched and the true total
    is unknowable without a separate request. The notice must claim neither a
    total nor an empty result set, and must still cost no extra API call.
    """
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    results = FakeSearchResults(make_search_items(5))

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = results

    result = github_search(query="test", max_results=max_results)

    assert not result.startswith("Error:")
    assert "No results found." not in result
    assert result.startswith(
        "... showing 0 of an unknown total — a max_results cap of 0 "
        "suppressed the output; raise max_results to see results."
    )
    assert results.total_count_reads == 0


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_empty_makes_no_total_count_call(
    mock_manager_cls: MagicMock,
) -> None:
    """A zero-result search never reads totalCount; a non-empty one reads it once.

    The read is skipped on the empty path not to save a request — page 1 was
    fetched and cached totalCount == 0 — but because the "No results found."
    render has no use for a total already known to be 0.
    """
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo

    empty_results = FakeSearchResults([])
    mock_mgr._github_client.search_issues.return_value = empty_results

    result = github_search(query="test")

    assert "No results found." in result
    assert empty_results.total_count_reads == 0

    non_empty_results = FakeSearchResults(make_search_items(3))
    mock_mgr._github_client.search_issues.return_value = non_empty_results

    github_search(query="test", max_results=3)

    assert non_empty_results.total_count_reads == 1
