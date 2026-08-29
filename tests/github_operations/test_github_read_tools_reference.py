"""Tests for reference_name support in the GitHub read-only MCP tools."""

from pathlib import Path
from typing import Any, Callable, Generator
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.server import (
    github_issue_list,
    github_issue_view,
    github_pr_view,
    github_search,
)
from mcp_workspace.server_reference_tools import set_reference_projects

from ._github_read_tools_helpers import make_issue, mock_pull

pytestmark = pytest.mark.usefixtures("setup_server")


@pytest.fixture
def reference_projects() -> Generator[None, None, None]:
    """Configure two reference projects with paths that do not exist.

    The paths are deliberately non-existent: a GitHub read must resolve through
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


def _configure_manager(mock_mgr: MagicMock) -> None:
    """Set up a mock IssueManager that satisfies all four read tools."""
    # pylint: disable=protected-access
    mock_mgr.get_issue.return_value = make_issue()
    mock_mgr.get_comments.return_value = []
    mock_mgr.list_issues.return_value = []
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/sibling"
    mock_repo.get_pull.return_value = mock_pull()
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = []


_TOOL_CASES: list[tuple[Callable[..., str], dict[str, Any]]] = [
    (github_issue_view, {"number": 42}),
    (github_issue_list, {}),
    (github_pr_view, {"number": 10}),
    (github_search, {"query": "x"}),
]
_TOOL_IDS = ["issue_view", "issue_list", "pr_view", "search"]


@pytest.mark.parametrize(("tool", "kwargs"), _TOOL_CASES, ids=_TOOL_IDS)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_reference_name_uses_repo_url(
    mock_manager_cls: MagicMock,
    tool: Callable[..., str],
    kwargs: dict[str, Any],
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """All four tools construct IssueManager with the reference project's URL."""
    mock_mgr = MagicMock()
    _configure_manager(mock_mgr)
    mock_manager_cls.return_value = mock_mgr

    tool(**kwargs, reference_name="sibling")

    assert mock_manager_cls.call_args.kwargs == {
        "repo_url": "https://github.com/owner/sibling"
    }


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_no_reference_name_uses_project_dir(
    mock_manager_cls: MagicMock, project_dir: Path
) -> None:
    """Without reference_name the workspace project_dir is used, unchanged."""
    mock_mgr = MagicMock()
    _configure_manager(mock_mgr)
    mock_manager_cls.return_value = mock_mgr

    github_issue_view(number=42)

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
    result = github_issue_view(number=42, reference_name="nourl")

    assert result == "Error: Reference project 'nourl' has no URL configured"
    mock_manager_cls.assert_not_called()


@patch("mcp_workspace.server_reference_tools.ensure_available")
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_reference_read_does_not_clone(
    mock_manager_cls: MagicMock,
    mock_ensure_available: MagicMock,
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """Reading from a reference project never clones its working tree."""
    mock_mgr = MagicMock()
    _configure_manager(mock_mgr)
    mock_manager_cls.return_value = mock_mgr

    github_issue_view(number=42, reference_name="sibling")

    mock_ensure_available.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_reference_name_scopes_search_query(
    mock_manager_cls: MagicMock,
    reference_projects: None,  # pylint: disable=unused-argument
) -> None:
    """github_search scopes to the reference repository in repo_url mode."""
    mock_mgr = MagicMock()
    _configure_manager(mock_mgr)
    mock_manager_cls.return_value = mock_mgr

    github_search(query="x", reference_name="sibling")

    # pylint: disable=protected-access
    sent_query = mock_mgr._github_client.search_issues.call_args.kwargs["query"]
    assert sent_query.startswith("repo:owner/sibling")
