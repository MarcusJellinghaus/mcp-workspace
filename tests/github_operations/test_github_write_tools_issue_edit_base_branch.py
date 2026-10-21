"""Tests for the Base Branch section guard in the ``github_issue_edit`` MCP tool."""

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.github_operations.issues.types import IssueData
from mcp_workspace.server import github_issue_edit, set_project_dir


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


def _make_manager(
    issue: IssueData | None = None,
    available_labels: list[dict[str, str]] | None = None,
    login: str = "marcus",
) -> MagicMock:
    """Create a mocked IssueManager with the calls the tool makes."""
    mock_mgr = MagicMock()
    mock_mgr.edit_issue.return_value = issue if issue is not None else _make_issue()
    mock_mgr.get_available_labels.return_value = available_labels or []
    mock_mgr.github_token = "test-token"
    mock_mgr._github_client.get_user.return_value.login = login
    return mock_mgr


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_rejects_malformed_base_branch(
    mock_manager_cls: MagicMock,
) -> None:
    """A multi-line Base Branch section is rejected before any manager call."""
    result = github_issue_edit(
        number=42,
        body="### Base Branch\n\nline1\nline2\n",
    )

    assert result.startswith("Error:")
    assert "line1" in result
    mock_manager_cls.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_accepts_valid_base_branch(
    mock_manager_cls: MagicMock,
) -> None:
    """A single-line Base Branch section is accepted."""
    mock_manager_cls.return_value = _make_manager(issue=_make_issue())

    result = github_issue_edit(number=42, body="### Base Branch\n\nfeature/v2\n")

    assert result.startswith("Updated issue")


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_accepts_body_without_base_branch_section(
    mock_manager_cls: MagicMock,
) -> None:
    """A body with no Base Branch heading at all is accepted."""
    mock_manager_cls.return_value = _make_manager(issue=_make_issue())

    result = github_issue_edit(number=42, body="Just a plain body.")

    assert result.startswith("Updated issue")


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_accepts_empty_base_branch_section(
    mock_manager_cls: MagicMock,
) -> None:
    """An empty Base Branch section is accepted."""
    mock_manager_cls.return_value = _make_manager(issue=_make_issue())

    result = github_issue_edit(number=42, body="### Base Branch\n\n### Next")

    assert result.startswith("Updated issue")


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_accepts_fenced_base_branch_heading(
    mock_manager_cls: MagicMock,
) -> None:
    """A Base Branch heading quoted only inside a code fence is not a section."""
    mock_manager_cls.return_value = _make_manager(issue=_make_issue())

    result = github_issue_edit(
        number=42,
        body="### Description\n\n```\n### Base Branch\n\nline1\nline2\n```\n",
    )

    assert result.startswith("Updated issue")


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_without_body_is_never_blocked(
    mock_manager_cls: MagicMock,
) -> None:
    """An edit that never touches body is never blocked by the Base Branch check."""
    mock_mgr = _make_manager(
        issue=_make_issue(labels=["bug"]), available_labels=[_label("bug")]
    )
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, add_labels=["bug"])

    assert not result.startswith("Error: `### Base Branch`")
    mock_mgr.edit_issue.assert_called_once()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_rejects_malformed_base_branch_crlf(
    mock_manager_cls: MagicMock,
) -> None:
    """CRLF line endings must not leak a trailing \\r into the error message."""
    result = github_issue_edit(
        number=42,
        body="### Base Branch\r\n\r\nline1\r\nline2\r\n",
    )

    assert result.startswith("Error:")
    assert "line1" in result
    assert "line1\r" not in result
    mock_manager_cls.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_accepts_valid_base_branch_crlf(
    mock_manager_cls: MagicMock,
) -> None:
    """A single-line Base Branch section with CRLF endings is accepted."""
    mock_manager_cls.return_value = _make_manager(issue=_make_issue())

    result = github_issue_edit(
        number=42,
        body="### Base Branch\r\n\r\nfeature/v2\r\n",
    )

    assert result.startswith("Updated issue")


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_with_flag_off_writes_malformed_base_branch(
    mock_manager_cls: MagicMock,
) -> None:
    """With the check disabled, the old pre-#320 behavior is preserved."""
    mock_manager_cls.return_value = _make_manager(issue=_make_issue())

    with patch("mcp_workspace.server._enforce_base_branch_format", False):
        result = github_issue_edit(
            number=42,
            body="### Base Branch\n\nline1\nline2\n",
        )

    assert result.startswith("Updated issue")
