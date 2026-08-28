"""Tests for GitHub read-only MCP tools in server.py."""

from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.github_operations import IssueIdentityMismatchError
from mcp_workspace.github_operations.issues.types import IssueData
from mcp_workspace.server import (
    github_issue_list,
    github_issue_view,
    github_pr_view,
    github_search,
    set_project_dir,
)

from ._github_read_tools_helpers import make_comment, make_issue, mock_pull


@pytest.fixture(autouse=True)
def setup_server(project_dir: Path) -> Generator[None, None, None]:
    """Setup the server with the project directory."""
    set_project_dir(project_dir)
    yield


# =============================================================================
# github_issue_view tests
# =============================================================================


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_view_basic(mock_manager_cls: MagicMock) -> None:
    """Returns formatted text with title, state, body."""
    issue = make_issue()
    mock_mgr = MagicMock()
    mock_mgr.get_issue.return_value = issue
    mock_mgr.get_comments.return_value = []
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_view(number=42)

    assert "#42" in result
    assert "Test issue" in result
    assert "open" in result
    assert "Issue body text" in result
    mock_mgr.get_issue.assert_called_once_with(42)


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_view_with_comments(mock_manager_cls: MagicMock) -> None:
    """Comments included when include_comments=True."""
    issue = make_issue()
    comments = [make_comment(body="Great work!")]
    mock_mgr = MagicMock()
    mock_mgr.get_issue.return_value = issue
    mock_mgr.get_comments.return_value = comments
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_view(number=42, include_comments=True)

    assert "Great work!" in result
    assert "Comments" in result
    mock_mgr.get_comments.assert_called_once_with(42)


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_view_without_comments(mock_manager_cls: MagicMock) -> None:
    """No comments when include_comments=False."""
    issue = make_issue()
    mock_mgr = MagicMock()
    mock_mgr.get_issue.return_value = issue
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_view(number=42, include_comments=False)

    assert "Test issue" in result
    mock_mgr.get_comments.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_view_not_found(mock_manager_cls: MagicMock) -> None:
    """Returns error text when issue number=0 (empty IssueData)."""
    empty_issue = IssueData(
        number=0,
        title="",
        body="",
        state="",
        labels=[],
        assignees=[],
        user=None,
        created_at=None,
        updated_at=None,
        url="",
        locked=False,
    )
    mock_mgr = MagicMock()
    mock_mgr.get_issue.return_value = empty_issue
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_view(number=999)

    assert "Error" in result
    assert "#999" in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_view_transferred(mock_manager_cls: MagicMock) -> None:
    """A transferred issue renders the transfer target with one Error: prefix."""
    mock_mgr = MagicMock()
    mock_mgr.get_issue.side_effect = IssueIdentityMismatchError(
        "Issue #72 was transferred to MarcusJellinghaus/mcp-workspace#220 "
        "— https://github.com/MarcusJellinghaus/mcp-workspace/issues/220"
    )
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_view(number=72)

    assert result == (
        "Error: Issue #72 was transferred to "
        "MarcusJellinghaus/mcp-workspace#220 "
        "— https://github.com/MarcusJellinghaus/mcp-workspace/issues/220"
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_view_error(mock_manager_cls: MagicMock) -> None:
    """Returns 'Error: ...' on exception."""
    mock_manager_cls.side_effect = RuntimeError("connection failed")

    result = github_issue_view(number=42)

    assert result == "Error: connection failed"


# =============================================================================
# github_issue_list tests
# =============================================================================


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_list_basic(mock_manager_cls: MagicMock) -> None:
    """Returns compact summary lines."""
    issues = [
        make_issue(number=1, title="First"),
        make_issue(number=2, title="Second"),
    ]
    mock_mgr = MagicMock()
    mock_mgr.list_issues.return_value = issues
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_list()

    assert "#1" in result
    assert "First" in result
    assert "#2" in result
    assert "Second" in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_list_empty(mock_manager_cls: MagicMock) -> None:
    """Returns 'No issues found.' for empty list."""
    mock_mgr = MagicMock()
    mock_mgr.list_issues.return_value = []
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_list()

    assert result == "No issues found."


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_list_with_filters(mock_manager_cls: MagicMock) -> None:
    """Verifies labels/assignee/since passed through to manager."""
    mock_mgr = MagicMock()
    mock_mgr.list_issues.return_value = []
    mock_manager_cls.return_value = mock_mgr

    github_issue_list(
        state="closed",
        labels=["bug", "urgent"],
        assignee="alice",
        since="2024-06-01T00:00:00",
        max_results=10,
    )

    mock_mgr.list_issues.assert_called_once_with(
        state="closed",
        labels=["bug", "urgent"],
        assignee="alice",
        since=datetime.fromisoformat("2024-06-01T00:00:00"),
        max_results=10,
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_list_error(mock_manager_cls: MagicMock) -> None:
    """Returns 'Error: ...' on exception."""
    mock_manager_cls.side_effect = RuntimeError("API down")

    result = github_issue_list()

    assert result == "Error: API down"


# =============================================================================
# github_pr_view tests
# =============================================================================


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_pr_view_basic(mock_manager_cls: MagicMock) -> None:
    """Returns formatted text with title, state, branches."""
    mock_repo = MagicMock()
    mock_pr = mock_pull()
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
    mock_pr = mock_pull()

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
    mock_pr = mock_pull()
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

    assert "Error" in result
    assert "repository" in result.lower()
    assert "https://gitlab.com/api/v3" in result


# =============================================================================
# github_search tests
# =============================================================================


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_basic(mock_manager_cls: MagicMock) -> None:
    """Returns compact summary lines with auto-scoped repo."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    item1 = MagicMock()
    item1.number = 1
    item1.title = "Bug fix"
    item1.state = "open"
    item1.labels = []
    item1.pull_request = None

    item2 = MagicMock()
    item2.number = 2
    item2.title = "Feature PR"
    item2.state = "open"
    item2.labels = []
    item2.pull_request = MagicMock()  # truthy = is a PR

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = [item1, item2]

    result = github_search(query="fix")

    assert "#1" in result
    assert "Bug fix" in result
    assert "#2" in result
    assert "Feature PR" in result
    assert "(auto-added: is:issue is:pull-request)" in result
    mock_mgr._github_client.search_issues.assert_called_once()
    call_args = mock_mgr._github_client.search_issues.call_args
    assert "repo:owner/repo" in call_args[1]["query"]
    assert "is:issue is:pull-request" in call_args[1]["query"]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_empty(mock_manager_cls: MagicMock) -> None:
    """Returns 'No results found.' for empty results."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = []

    result = github_search(query="nonexistent")

    assert "No results found." in result
    assert "(auto-added: is:issue is:pull-request)" in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_with_qualifiers(mock_manager_cls: MagicMock) -> None:
    """Verifies state/labels/assignee/sort/order passed through."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = []

    github_search(
        query="bug",
        state="open",
        labels=["bug", "urgent"],
        assignee="alice",
        sort="created",
        order="desc",
    )

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    assert "repo:owner/repo" in call_kwargs["query"]
    assert "is:issue is:pull-request" in call_kwargs["query"]
    assert call_kwargs.get("state") == "open"
    assert call_kwargs.get("sort") == "created"
    assert call_kwargs.get("order") == "desc"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_issue_vs_pr_indicator(mock_manager_cls: MagicMock) -> None:
    """Correct Issue/PR indicator in results."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    issue_item = MagicMock()
    issue_item.number = 1
    issue_item.title = "A bug"
    issue_item.state = "open"
    issue_item.labels = []
    issue_item.pull_request = None

    pr_item = MagicMock()
    pr_item.number = 2
    pr_item.title = "A PR"
    pr_item.state = "open"
    pr_item.labels = []
    pr_item.pull_request = MagicMock()

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = [issue_item, pr_item]

    result = github_search(query="test")

    result_lines = [
        line for line in result.strip().split("\n") if not line.startswith("(")
    ]
    assert "[Issue]" in result_lines[0]
    assert "[PR]" in result_lines[1]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_max_results_cap(mock_manager_cls: MagicMock) -> None:
    """Results capped at max_results."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    items = []
    for i in range(10):
        item = MagicMock()
        item.number = i + 1
        item.title = f"Item {i + 1}"
        item.state = "open"
        item.labels = []
        item.pull_request = None
        items.append(item)

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = items

    result = github_search(query="test", max_results=3)

    assert "#1" in result
    assert "#3" in result
    # Item 4+ should not appear in the output lines
    # (only 3 items are passed to the formatter)
    lines = [line for line in result.strip().split("\n") if line.startswith("#")]
    assert len(lines) == 3


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_error(mock_manager_cls: MagicMock) -> None:
    """Returns 'Error: ...' on exception."""
    mock_manager_cls.side_effect = RuntimeError("API down")

    result = github_search(query="test")

    assert result == "Error: API down"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_no_repo(mock_manager_cls: MagicMock) -> None:
    """Returns error when repository not accessible."""
    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = None
    mock_mgr._repo_identifier.api_base_url = "https://gitlab.com/api/v3"

    result = github_search(query="test")

    assert "Error" in result
    assert "repository" in result.lower()
    assert "https://gitlab.com/api/v3" in result


@pytest.mark.parametrize(
    ("query", "should_inject", "description"),
    [
        ("MCP migration", True, "no qualifier → injects"),
        ("MCP migration is:issue", False, "explicit is:issue → no inject"),
        ("fix is:pull-request", False, "explicit is:pull-request → no inject"),
        ("fix Is:Issue", False, "mixed case → no inject"),
        ("basis:issue problem", True, "substring containing is:issue → injects"),
    ],
    ids=lambda val: val if isinstance(val, str) and "→" in val else "",
)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_qualifier_injection(
    mock_manager_cls: MagicMock,
    query: str,
    should_inject: bool,
    description: str,
) -> None:
    """Qualifier auto-injection depending on query content."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    item = MagicMock()
    item.number = 1
    item.title = "Result"
    item.state = "open"
    item.labels = []
    item.pull_request = None

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = [item]

    result = github_search(query=query)

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    sent_query = call_kwargs["query"]

    if should_inject:
        assert "is:issue is:pull-request" in sent_query
        assert "(auto-added: is:issue is:pull-request)" in result
    else:
        assert "is:issue is:pull-request" not in sent_query
        assert "(auto-added: is:issue is:pull-request)" not in result
