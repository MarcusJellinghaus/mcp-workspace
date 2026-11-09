"""Tests for the github_issue_set_status MCP tool."""

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from mcp_workspace.github_operations.caching._store import cache_file_path
from mcp_workspace.github_operations.issues.types import (
    IssueData,
    create_empty_issue_data,
)
from mcp_workspace.github_operations.labels_manager import LabelData
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.server import (
    github_issue_create,
    github_issue_edit,
    github_issue_set_status,
)
from mcp_workspace.server_reference_tools import set_reference_projects
from mcp_workspace.utils.repo_identifier import RepoIdentifier

pytestmark = pytest.mark.usefixtures("setup_server")

_REPO = RepoIdentifier("owner", "repo")
_GUARD_ERROR = (
    "Error: these tools do not modify status-* labels "
    "(status-01:created). Use github_issue_set_status"
)


@pytest.fixture
def reference_projects() -> Generator[None, None, None]:
    """Configure a reference project with a URL and one without.

    The paths do not exist: the tool must resolve through the configured URL
    and never touch (or clone) a working tree.
    """
    set_reference_projects(
        {
            "sibling": ReferenceProject(
                name="sibling",
                path=Path("/does/not/exist"),
                url="https://github.com/owner/sibling",
            ),
            "nourl": ReferenceProject(
                name="nourl", path=Path("/does/not/exist/2"), url=None
            ),
        }
    )
    yield
    set_reference_projects({})


def _label(name: str) -> LabelData:
    """Build a LabelData with the given name."""
    return LabelData(
        name=name,
        color="ededed",
        description=f"{name} description",
        url=f"https://api.github.com/repos/owner/repo/labels/{name}",
    )


def _issue(labels: list[str], number: int = 42) -> IssueData:
    """Build an open IssueData carrying ``labels``."""
    return IssueData(
        number=number,
        title="T",
        body="",
        state="open",
        labels=labels,
        assignees=[],
        user="octocat",
        created_at="2024-01-01T00:00:00",
        updated_at=None,
        url=f"https://github.com/owner/repo/issues/{number}",
        locked=False,
        author_association="OWNER",
    )


def _make_manager() -> MagicMock:
    """Mock IssueManager moving #42 from status-01:created to status-02:planning."""
    mock_mgr = MagicMock()
    # A real identifier: a MagicMock cache_safe_name is no valid cache file name
    mock_mgr.repo_identifier = _REPO
    mock_mgr.get_available_labels.return_value = [
        _label("bug"),
        _label("status-01:created"),
        _label("status-02:planning"),
    ]
    mock_mgr.get_issue_for_status.return_value = _issue(["bug", "status-01:created"])
    mock_mgr.set_labels.return_value = _issue(["bug", "status-02:planning"])
    return mock_mgr


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_workspace_issue_status_changed(
    mock_manager_cls: MagicMock, project_dir: Path
) -> None:
    """A workspace issue moves to the new status and reports the labels."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_set_status(number=42, status="status-02:planning")

    assert result == (
        "Issue #42 status: status-01:created → status-02:planning\n"
        "Labels: bug, status-02:planning"
    )
    assert mock_manager_cls.call_args.kwargs == {"project_dir": project_dir}
    mock_mgr.set_labels.assert_called_once_with(42, "bug", "status-02:planning")


@patch("mcp_workspace.server_reference_tools.ensure_available")
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_reference_project_uses_url_without_clone(
    mock_manager_cls: MagicMock,
    mock_ensure_available: MagicMock,
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """A reference project's issue is changed through its URL, never a clone."""
    mock_manager_cls.return_value = _make_manager()

    result = github_issue_set_status(
        number=42, status="status-02:planning", reference_name="sibling"
    )

    assert result.startswith("Issue #42 status: status-01:created → ")
    assert mock_manager_cls.call_args.kwargs == {
        "repo_url": "https://github.com/owner/sibling"
    }
    mock_ensure_available.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_reference_project_without_url_returns_error(
    mock_manager_cls: MagicMock,
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """A reference project with no URL yields the same error as other tools."""
    result = github_issue_set_status(
        number=42, status="status-02:planning", reference_name="nourl"
    )

    assert result == "Error: Reference project 'nourl' has no URL configured"
    mock_manager_cls.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_pull_request_rejected(mock_manager_cls: MagicMock) -> None:
    """A pull request number is reported as an error and nothing is written."""
    mock_mgr = _make_manager()
    mock_mgr.get_issue_for_status.side_effect = ValueError(
        "#5 is a pull request, not an issue"
    )
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_set_status(number=5, status="status-02:planning")

    assert result == "Error: #5 is a pull request, not an issue"
    mock_mgr.set_labels.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_not_found_returns_github_message(mock_manager_cls: MagicMock) -> None:
    """A 404 on the issue read is rendered with GitHub's message."""
    mock_mgr = _make_manager()
    mock_mgr.get_issue_for_status.side_effect = GithubException(
        404, {"message": "Not Found"}, None
    )
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_set_status(number=999, status="status-02:planning")

    assert result.startswith("Error:")
    assert "Not Found" in result
    mock_mgr.set_labels.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_unconfirmed_write(mock_manager_cls: MagicMock) -> None:
    """An empty IssueData from set_labels is reported as unconfirmed."""
    mock_mgr = _make_manager()
    mock_mgr.set_labels.return_value = create_empty_issue_data()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_set_status(number=42, status="status-02:planning")

    assert result == (
        "Error: write to issue #42 failed or unconfirmed — "
        "re-check with github_issue_view"
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_success_updates_coordinator_issue_cache(
    mock_manager_cls: MagicMock,
) -> None:
    """After a successful write the coordinator issue cache holds the new labels."""
    issues_path = cache_file_path(_REPO, "issues")
    issues_path.parent.mkdir(parents=True, exist_ok=True)
    issues_path.write_text(
        json.dumps(
            {
                "last_checked": "2025-01-03T10:30:00Z",
                "issues": {"42": _issue(["bug", "status-01:created"])},
            }
        ),
        encoding="utf-8",
    )
    mock_manager_cls.return_value = _make_manager()

    github_issue_set_status(number=42, status="status-02:planning")

    cached = json.loads(issues_path.read_text(encoding="utf-8"))
    assert cached["issues"]["42"]["labels"] == ["bug", "status-02:planning"]


@pytest.mark.parametrize("reference_name", [None, "sibling"], ids=["ws", "ref"])
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_create_status_label_points_at_set_status(
    mock_manager_cls: MagicMock,
    reference_name: str | None,
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """github_issue_create rejects status-* and names github_issue_set_status."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(
        title="T", labels=["status-01:created"], reference_name=reference_name
    )

    assert result == _GUARD_ERROR
    mock_mgr.create_issue.assert_not_called()


@pytest.mark.parametrize("reference_name", [None, "sibling"], ids=["ws", "ref"])
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_edit_status_label_points_at_set_status(
    mock_manager_cls: MagicMock,
    reference_name: str | None,
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """github_issue_edit rejects status-* and names github_issue_set_status."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(
        number=42, add_labels=["status-01:created"], reference_name=reference_name
    )

    assert result == _GUARD_ERROR
    mock_mgr.edit_issue.assert_not_called()
