"""Tests for the GitHub issue read-only MCP tools in server.py."""

from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.github_operations import IssueIdentityMismatchError
from mcp_workspace.github_operations.issues.types import CommentData, IssueData
from mcp_workspace.server import github_issue_list, github_issue_view, set_project_dir


@pytest.fixture(autouse=True)
def setup_server(project_dir: Path) -> Generator[None, None, None]:
    """Setup the server with the project directory."""
    set_project_dir(project_dir)
    yield


def _make_issue(
    number: int = 42,
    title: str = "Test issue",
    body: str = "Issue body text",
    state: str = "open",
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> IssueData:
    """Create an IssueData for testing."""
    return IssueData(
        number=number,
        title=title,
        body=body,
        state=state,
        labels=labels or ["bug"],
        assignees=assignees or ["alice"],
        user="alice",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-02T00:00:00",
        url="https://github.com/test/repo/issues/42",
        locked=False,
    )


def _make_comment(
    comment_id: int = 1,
    body: str = "A comment",
    user: str = "bob",
) -> CommentData:
    """Create a CommentData for testing."""
    return CommentData(
        id=comment_id,
        body=body,
        user=user,
        created_at="2024-01-03T00:00:00",
        updated_at=None,
        url="https://github.com/test/repo/issues/42#issuecomment-1",
    )


# =============================================================================
# github_issue_view tests
# =============================================================================


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_view_basic(mock_manager_cls: MagicMock) -> None:
    """Returns formatted text with title, state, body."""
    issue = _make_issue()
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
    issue = _make_issue()
    comments = [_make_comment(body="Great work!")]
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
    issue = _make_issue()
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
        _make_issue(number=1, title="First"),
        _make_issue(number=2, title="Second"),
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
        max_results=11,
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_list_notice_when_more_exist(mock_manager_cls: MagicMock) -> None:
    """The surplus over-fetched item triggers the truncation notice."""
    issues = [_make_issue(number=i, title=f"Issue {i}") for i in range(4)]
    mock_mgr = MagicMock()
    mock_mgr.list_issues.return_value = issues
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_list(max_results=3)

    assert "showing 3 of 3+ results" in result
    issue_lines = [line for line in result.splitlines() if line.startswith("#")]
    assert len(issue_lines) == 3


@pytest.mark.parametrize("max_results", [0, -1])
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_list_non_positive_max_results(
    mock_manager_cls: MagicMock, max_results: int
) -> None:
    """A zero or negative cap lists nothing and never reports a negative count."""
    mock_mgr = MagicMock()
    mock_mgr.list_issues.return_value = [_make_issue(number=1, title="First")]
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_list(max_results=max_results)

    assert mock_mgr.list_issues.call_args.kwargs["max_results"] == 1
    # The over-fetch found an issue, so the notice must not claim none exist.
    assert "No issues found." not in result
    assert result == "... showing 0 of 0+ results — raise max_results to see them."


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_list_error(mock_manager_cls: MagicMock) -> None:
    """Returns 'Error: ...' on exception."""
    mock_manager_cls.side_effect = RuntimeError("API down")

    result = github_issue_list()

    assert result == "Error: API down"
