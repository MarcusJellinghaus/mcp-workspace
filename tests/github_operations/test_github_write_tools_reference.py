"""Tests for reference_name support in the GitHub write and label MCP tools."""

from pathlib import Path
from typing import Any, Callable, Generator
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.github_operations.issues.types import (
    CommentData,
    IssueData,
    create_empty_issue_data,
)
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.server import (
    github_issue_comment,
    github_issue_create,
    github_label_list,
)
from mcp_workspace.server_reference_tools import set_reference_projects

pytestmark = pytest.mark.usefixtures("setup_server")


@pytest.fixture
def reference_projects() -> Generator[None, None, None]:
    """Configure two reference projects with paths that do not exist.

    The paths are deliberately non-existent: a GitHub call must resolve through
    the configured URL and never touch (or clone) a working tree.
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


def _make_comment(comment_id: int = 1) -> CommentData:
    """Build a CommentData; ``comment_id=0`` is the empty-comment sentinel."""
    return CommentData(
        id=comment_id,
        body="hi",
        user="octocat",
        created_at="2024-01-01T00:00:00",
        updated_at=None,
        url="https://github.com/owner/sibling/issues/42#issuecomment-1",
    )


def _make_issue() -> IssueData:
    """Build a created-issue IssueData with a non-zero number."""
    return IssueData(
        number=42,
        title="T",
        body="",
        state="open",
        labels=[],
        assignees=[],
        user="octocat",
        created_at="2024-01-01T00:00:00",
        updated_at=None,
        url="https://github.com/owner/sibling/issues/42",
        locked=False,
    )


def _make_manager() -> MagicMock:
    """Create a mock IssueManager that satisfies the covered tools."""
    mock_mgr = MagicMock()
    mock_mgr.get_available_labels.return_value = [
        {
            "name": "bug",
            "color": "d73a4a",
            "description": "Something isn't working",
            "url": "https://api.github.com/repos/owner/sibling/labels/bug",
        }
    ]
    # Real TypedDicts, not MagicMocks: comment["id"] and issue["number"] must be
    # genuinely truthy rather than opaquely truthy.
    mock_mgr.add_comment.return_value = _make_comment()
    mock_mgr.create_issue.return_value = _make_issue()
    # pylint: disable-next=protected-access
    mock_mgr._github_client.get_user.return_value.login = "octocat"
    return mock_mgr


_TOOL_CASES: list[tuple[Callable[..., str], dict[str, Any]]] = [
    (github_label_list, {}),
    (github_issue_comment, {"number": 42, "body": "hi"}),
    (github_issue_create, {"title": "T"}),
]
_TOOL_IDS = ["label_list", "issue_comment", "issue_create"]


@pytest.mark.parametrize(("tool", "kwargs"), _TOOL_CASES, ids=_TOOL_IDS)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_reference_name_uses_repo_url(
    mock_manager_cls: MagicMock,
    tool: Callable[..., str],
    kwargs: dict[str, Any],
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """The tools construct IssueManager with the reference project's URL."""
    mock_manager_cls.return_value = _make_manager()

    tool(**kwargs, reference_name="sibling")

    assert mock_manager_cls.call_args.kwargs == {
        "repo_url": "https://github.com/owner/sibling"
    }


@pytest.mark.parametrize(("tool", "kwargs"), _TOOL_CASES, ids=_TOOL_IDS)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_no_reference_name_uses_project_dir(
    mock_manager_cls: MagicMock,
    tool: Callable[..., str],
    kwargs: dict[str, Any],
    project_dir: Path,
) -> None:
    """Without reference_name the workspace project_dir is used, unchanged."""
    mock_manager_cls.return_value = _make_manager()

    tool(**kwargs)

    assert mock_manager_cls.call_args.kwargs == {"project_dir": project_dir}


@pytest.mark.parametrize(("tool", "kwargs"), _TOOL_CASES, ids=_TOOL_IDS)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_unknown_reference_name_returns_error(
    mock_manager_cls: MagicMock,
    tool: Callable[..., str],
    kwargs: dict[str, Any],
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """An unknown reference name is returned as an error string, not raised."""
    result = tool(**kwargs, reference_name="nope")

    assert result == "Error: Reference project 'nope' not found"
    mock_manager_cls.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_reference_project_without_url_returns_error(
    mock_manager_cls: MagicMock,
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """A reference project with no configured URL yields an error string."""
    result = github_label_list(reference_name="nourl")

    assert result == "Error: Reference project 'nourl' has no URL configured"
    mock_manager_cls.assert_not_called()


@patch("mcp_workspace.server_reference_tools.ensure_available")
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_reference_access_does_not_clone(
    mock_manager_cls: MagicMock,
    mock_ensure_available: MagicMock,
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """Targeting a reference project never clones its working tree."""
    mock_manager_cls.return_value = _make_manager()

    github_label_list(reference_name="sibling")

    mock_ensure_available.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_comment_failure_names_reference_project(
    mock_manager_cls: MagicMock,
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """A failed cross-repo comment says which reference project it targeted."""
    mock_mgr = _make_manager()
    mock_mgr.add_comment.return_value = _make_comment(comment_id=0)
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_comment(number=42, body="hi", reference_name="sibling")

    assert result == (
        "Error: failed to add comment to issue #42 in reference project 'sibling'"
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_comment_failure_without_reference_is_unchanged(
    mock_manager_cls: MagicMock,
) -> None:
    """The workspace failure message stays byte-identical to today's."""
    mock_mgr = _make_manager()
    mock_mgr.add_comment.return_value = _make_comment(comment_id=0)
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_comment(number=42, body="hi")

    assert result == "Error: failed to add comment to issue #42"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_status_guard_points_at_reference_checkout(
    mock_manager_cls: MagicMock,
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """The status-* guard says whose checkout can apply the label."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(
        title="T", labels=["status-01:created"], reference_name="sibling"
    )

    assert "sibling" in result
    assert "own checkout" in result
    mock_mgr.get_available_labels.assert_not_called()
    mock_mgr.create_issue.assert_not_called()


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        (["bugg"], "Error: unknown label(s) in reference project 'sibling': bugg"),
        (
            ["bugg", "bugz"],
            "Error: unknown label(s) in reference project 'sibling': bugg, bugz",
        ),
    ],
    ids=["one", "two"],
)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_unknown_label_names_reference_project(
    mock_manager_cls: MagicMock,
    labels: list[str],
    expected: str,
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """Unknown labels name the reference project before the label list.

    The two-label case is the point: with the suffix ahead of the colon the
    list stays terminal, so 'sibling' cannot be misread as a third label.
    """
    mock_manager_cls.return_value = _make_manager()

    result = github_issue_create(title="T", labels=labels, reference_name="sibling")

    assert result == expected


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_create_failure_names_reference_project(
    mock_manager_cls: MagicMock,
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """A swallowed cross-repo creation failure names the target project."""
    mock_mgr = _make_manager()
    mock_mgr.create_issue.return_value = create_empty_issue_data()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_create(title="T", reference_name="sibling")

    assert result == (
        "Error: issue creation failed - no issue was created "
        "in reference project 'sibling'"
    )
