"""Tests for the GitHub issue write MCP tools in server.py.

Covers ``github_issue_create``, ``github_issue_comment`` and the two shared
helpers ``_check_labels`` and ``_resolve_assignees``.
"""

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from mcp_workspace import server as server_module
from mcp_workspace.github_operations.issues.types import (
    CommentData,
    IssueData,
    create_empty_issue_data,
)
from mcp_workspace.server import (
    github_issue_comment,
    github_issue_create,
    set_project_dir,
)


@pytest.fixture(autouse=True)
def setup_server(project_dir: Path) -> Generator[None, None, None]:
    """Setup the server with the project directory."""
    set_project_dir(project_dir)
    yield


@pytest.fixture(autouse=True)
def reset_login_cache() -> Generator[None, None, None]:
    """Clear the cached '@me' login so tests never leak it into each other."""
    server_module._login_cache.clear()
    yield
    server_module._login_cache.clear()


def _make_issue(
    number: int = 42,
    title: str = "Test issue",
    body: str = "Issue body text",
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> IssueData:
    """Create an IssueData for testing."""
    return IssueData(
        number=number,
        title=title,
        body=body,
        state="open",
        labels=labels or [],
        assignees=assignees or [],
        user="alice",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-02T00:00:00",
        url="https://github.com/test/repo/issues/42",
        locked=False,
    )


def _label(name: str) -> dict[str, str]:
    """Create a LabelData-shaped dict for testing."""
    return {"name": name, "color": "d73a4a", "description": "", "url": ""}


def _make_comment(comment_id: int = 1, body: str = "A comment") -> CommentData:
    """Create a CommentData for testing."""
    return CommentData(
        id=comment_id,
        body=body,
        user="alice",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
        url="https://github.com/test/repo/issues/42#issuecomment-1",
    )


def _make_manager(
    issue: IssueData | None = None,
    available_labels: list[dict[str, str]] | None = None,
    login: str = "marcus",
) -> MagicMock:
    """Create a mocked IssueManager with the calls the tool makes."""
    mock_mgr = MagicMock()
    mock_mgr.create_issue.return_value = issue if issue is not None else _make_issue()
    mock_mgr.get_available_labels.return_value = available_labels or []
    mock_mgr._github_client.get_user.return_value.login = login
    return mock_mgr


# =============================================================================
# github_issue_create tests
# =============================================================================


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_happy_path(mock_manager_cls: MagicMock) -> None:
    """Reports the new issue number and URL, and forwards title and body."""
    mock_manager_cls.return_value = _make_manager()

    result = github_issue_create(title="Test issue", body="Issue body text")

    assert result.splitlines()[0] == (
        "Created issue #42 — https://github.com/test/repo/issues/42"
    )
    kwargs = mock_manager_cls.return_value.create_issue.call_args.kwargs
    assert kwargs["title"] == "Test issue"
    assert kwargs["body"] == "Issue body text"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_empty_sentinel_is_an_error(
    mock_manager_cls: MagicMock,
) -> None:
    """The empty-IssueData sentinel must not read as success."""
    mock_manager_cls.return_value = _make_manager(issue=create_empty_issue_data())

    result = github_issue_create(title="Test issue")

    assert result.startswith("Error:")
    assert "Created" not in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_exception_is_reported(
    mock_manager_cls: MagicMock,
) -> None:
    """An exception from the library is rendered as an error string."""
    mock_mgr = _make_manager()
    mock_mgr.create_issue.side_effect = ValueError("Issue title cannot be empty")
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(title="   ")

    assert result == "Error: Issue title cannot be empty"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_rejects_status_label(
    mock_manager_cls: MagicMock,
) -> None:
    """status-* labels are rejected before any API call is made."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(title="Test issue", labels=["status-01:created"])

    assert result.startswith("Error:")
    assert "status-01:created" in result
    assert "set-status" in result
    mock_mgr.create_issue.assert_not_called()
    mock_mgr.get_available_labels.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_rejects_unknown_label(
    mock_manager_cls: MagicMock,
) -> None:
    """A typo in a label name is rejected rather than creating the label."""
    mock_mgr = _make_manager(available_labels=[_label("bug")])
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(title="Test issue", labels=["bugg"])

    assert result.startswith("Error:")
    assert "bugg" in result
    mock_mgr.create_issue.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_accepts_known_label(
    mock_manager_cls: MagicMock,
) -> None:
    """A known label passes validation and reaches create_issue."""
    mock_mgr = _make_manager(
        issue=_make_issue(labels=["bug"]), available_labels=[_label("bug")]
    )
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(title="Test issue", labels=["bug"])

    assert result.startswith("Created issue #42")
    assert mock_mgr.create_issue.call_args.kwargs["labels"] == ["bug"]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_without_labels_skips_lookup(
    mock_manager_cls: MagicMock,
) -> None:
    """No labels means no label lookup — the check costs nothing."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(title="Test issue")

    assert result.startswith("Created issue #42")
    mock_mgr.get_available_labels.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_label_lookup_failure_is_not_unknown_label(
    mock_manager_cls: MagicMock,
) -> None:
    """A failed label lookup reports the API error, never 'unknown label'."""
    mock_mgr = _make_manager()
    mock_mgr.get_available_labels.side_effect = GithubException(
        500, {"message": "Internal Server Error"}, None
    )
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(title="Test issue", labels=["bug"])

    assert result.startswith("Error:")
    assert "500" in result
    assert "unknown label" not in result
    mock_mgr.create_issue.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_empty_label_list_still_rejects(
    mock_manager_cls: MagicMock,
) -> None:
    """An empty label list means the repo has no labels, so an add is unknown."""
    mock_mgr = _make_manager(available_labels=[])
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(title="Test issue", labels=["bug"])

    assert result == "Error: unknown label(s): bug"
    mock_mgr.create_issue.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_accepts_differently_cased_label(
    mock_manager_cls: MagicMock,
) -> None:
    """GitHub label names are case-insensitive, so 'Bug' is not a typo."""
    mock_mgr = _make_manager(
        issue=_make_issue(labels=["bug"]), available_labels=[_label("bug")]
    )
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(title="Test issue", labels=["Bug"])

    assert result.startswith("Created issue #42")
    assert mock_mgr.create_issue.call_args.kwargs["labels"] == ["Bug"]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_rejects_differently_cased_status_label(
    mock_manager_cls: MagicMock,
) -> None:
    """The status guard is case-insensitive too, so 'Status-' cannot slip past."""
    mock_mgr = _make_manager(available_labels=[_label("Status-01:created")])
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(title="Test issue", labels=["Status-01:created"])

    assert result.startswith("Error:")
    assert "set-status" in result
    mock_mgr.create_issue.assert_not_called()
    mock_mgr.get_available_labels.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_reports_resulting_assignees(
    mock_manager_cls: MagicMock,
) -> None:
    """The resulting assignee list is reported, mirroring github_issue_edit."""
    mock_manager_cls.return_value = _make_manager(
        issue=_make_issue(assignees=["alice"])
    )

    result = github_issue_create(title="Test issue", assignees=["alice"])

    assert result.splitlines() == [
        "Created issue #42 — https://github.com/test/repo/issues/42",
        "Labels: (none)",
        "Assignees: alice",
    ]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_reports_resulting_labels(
    mock_manager_cls: MagicMock,
) -> None:
    """GitHub can drop a label silently — the resulting set must be reported."""
    mock_manager_cls.return_value = _make_manager(
        issue=_make_issue(labels=["bug"]),
        available_labels=[_label("bug"), _label("enhancement")],
    )

    result = github_issue_create(title="Test issue", labels=["bug", "enhancement"])

    assert result.splitlines() == [
        "Created issue #42 — https://github.com/test/repo/issues/42",
        "Labels: bug",
        "Assignees: (none)",
    ]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_shows_silently_dropped_assignee(
    mock_manager_cls: MagicMock,
) -> None:
    """GitHub drops a non-assignable login without error — the caller must see it."""
    mock_manager_cls.return_value = _make_manager(issue=_make_issue(assignees=[]))

    result = github_issue_create(title="Test issue", assignees=["not-a-member"])

    assert result.startswith("Created issue #42")
    assert "Assignees: (none)" in result
    assert "not-a-member" not in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_resolves_me_assignee(
    mock_manager_cls: MagicMock,
) -> None:
    """'@me' is resolved to the authenticated login before the write."""
    mock_mgr = _make_manager(login="marcus")
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(title="Test issue", assignees=["@me"])

    assert result.startswith("Created issue #42")
    assert mock_mgr.create_issue.call_args.kwargs["assignees"] == ["marcus"]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_caches_me_lookup(mock_manager_cls: MagicMock) -> None:
    """The '@me' login is resolved once per process, not once per call."""
    mock_mgr = _make_manager(login="marcus")
    mock_manager_cls.return_value = mock_mgr

    github_issue_create(title="First", assignees=["@me"])
    github_issue_create(title="Second", assignees=["@me"])

    mock_mgr._github_client.get_user.assert_called_once()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_me_lookup_is_per_host(
    mock_manager_cls: MagicMock,
) -> None:
    """A second GitHub host resolves '@me' itself, not from the first's cache.

    The same token names a different user on each host, so a reference project
    elsewhere must not inherit the workspace host's login.
    """
    workspace = _make_manager(login="marcus")
    workspace._repo_identifier.api_base_url = "https://api.github.com"
    other_host = _make_manager(login="marcus-ghe")
    other_host._repo_identifier.api_base_url = "https://ghe.example.com/api/v3"

    mock_manager_cls.return_value = workspace
    github_issue_create(title="First", assignees=["@me"])
    mock_manager_cls.return_value = other_host
    github_issue_create(title="Second", assignees=["@me"])

    assert workspace.create_issue.call_args.kwargs["assignees"] == ["marcus"]
    assert other_host.create_issue.call_args.kwargs["assignees"] == ["marcus-ghe"]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_create_explicit_assignee_skips_lookup(
    mock_manager_cls: MagicMock,
) -> None:
    """A named assignee needs no authenticated-user lookup."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(title="Test issue", assignees=["alice"])

    assert result.startswith("Created issue #42")
    assert mock_mgr.create_issue.call_args.kwargs["assignees"] == ["alice"]
    mock_mgr._github_client.get_user.assert_not_called()


# =============================================================================
# github_issue_comment tests
# =============================================================================


class TestGithubIssueComment:
    """Tests for the ``github_issue_comment`` MCP tool."""

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_happy_path(self, mock_manager_cls: MagicMock) -> None:
        """Reports the comment URL and forwards number and body unchanged."""
        mock_mgr = MagicMock()
        mock_mgr.add_comment.return_value = _make_comment()
        mock_manager_cls.return_value = mock_mgr

        result = github_issue_comment(number=42, body="A comment")

        assert result.splitlines()[0] == (
            "Added comment to issue #42 — "
            "https://github.com/test/repo/issues/42#issuecomment-1"
        )
        mock_mgr.add_comment.assert_called_once_with(42, "A comment")

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_empty_sentinel_is_an_error(self, mock_manager_cls: MagicMock) -> None:
        """The empty-CommentData sentinel (id == 0) must not read as success."""
        mock_mgr = MagicMock()
        mock_mgr.add_comment.return_value = _make_comment(comment_id=0, body="")
        mock_manager_cls.return_value = mock_mgr

        result = github_issue_comment(number=42, body="A comment")

        assert result.startswith("Error:")
        assert "Added comment" not in result

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_empty_body_value_error_is_reported(
        self, mock_manager_cls: MagicMock
    ) -> None:
        """The library's own empty-body check surfaces as an error string."""
        mock_mgr = MagicMock()
        mock_mgr.add_comment.side_effect = ValueError("Comment body cannot be empty")
        mock_manager_cls.return_value = mock_mgr

        result = github_issue_comment(number=42, body="   ")

        assert result == "Error: Comment body cannot be empty"

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_exception_is_reported(self, mock_manager_cls: MagicMock) -> None:
        """An arbitrary exception from the library is rendered as an error."""
        mock_mgr = MagicMock()
        mock_mgr.add_comment.side_effect = GithubException(
            403, {"message": "Resource not accessible by integration"}, None
        )
        mock_manager_cls.return_value = mock_mgr

        result = github_issue_comment(number=42, body="A comment")

        assert result.startswith("Error:")
        assert "403" in result

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_multiline_body_passes_through_unchanged(
        self, mock_manager_cls: MagicMock
    ) -> None:
        """Accepting the body inline is the point — no heredoc, no mangling."""
        body = "## Review\n\n- [x] first\n- [ ] second\n\nDone.\n"
        mock_mgr = MagicMock()
        mock_mgr.add_comment.return_value = _make_comment(body=body)
        mock_manager_cls.return_value = mock_mgr

        result = github_issue_comment(number=42, body=body)

        assert result.startswith("Added comment to issue #42")
        assert mock_mgr.add_comment.call_args.args == (42, body)
