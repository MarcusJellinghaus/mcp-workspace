"""Tests for the label and pull-request MCP tools in server.py.

Covers ``github_label_list``.
"""

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from mcp_workspace.server import github_label_list, set_project_dir


@pytest.fixture(autouse=True)
def setup_server(project_dir: Path) -> Generator[None, None, None]:
    """Setup the server with the project directory."""
    set_project_dir(project_dir)
    yield


def _label(
    name: str,
    color: str = "d73a4a",
    description: str = "",
) -> dict[str, str]:
    """Create a LabelData-shaped dict for testing."""
    return {
        "name": name,
        "color": color,
        "description": description,
        "url": f"https://api.github.com/repos/test/repo/labels/{name}",
    }


def _make_manager(labels: list[dict[str, str]] | None = None) -> MagicMock:
    """Create a mocked IssueManager returning the given repository labels."""
    mock_mgr = MagicMock()
    mock_mgr.get_available_labels.return_value = labels if labels is not None else []
    return mock_mgr


_LABELS = [
    _label("bug", "d73a4a", "Something isn't working"),
    _label("enhancement", "a2eeef", "New feature or request"),
]


# =============================================================================
# github_label_list tests
# =============================================================================


class TestGithubLabelList:
    """Tests for the ``github_label_list`` MCP tool."""

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_lists_all_labels(self, mock_manager_cls: MagicMock) -> None:
        """Without a search every label is rendered on its own line."""
        mock_manager_cls.return_value = _make_manager(_LABELS)

        result = github_label_list()

        assert result.splitlines() == [
            "bug  #d73a4a  Something isn't working",
            "enhancement  #a2eeef  New feature or request",
        ]

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_search_matches_name(self, mock_manager_cls: MagicMock) -> None:
        """A search matching a label name returns only that label."""
        mock_manager_cls.return_value = _make_manager(_LABELS)

        result = github_label_list(search="bug")

        assert result == "bug  #d73a4a  Something isn't working"

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_search_matches_description_only(self, mock_manager_cls: MagicMock) -> None:
        """A search matching only the description still returns the label."""
        mock_manager_cls.return_value = _make_manager(_LABELS)

        result = github_label_list(search="New feature")

        assert result == "enhancement  #a2eeef  New feature or request"

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_search_is_case_insensitive(self, mock_manager_cls: MagicMock) -> None:
        """Matching ignores letter case on both sides."""
        mock_manager_cls.return_value = _make_manager(_LABELS)

        result = github_label_list(search="ENHANCEment")

        assert result == "enhancement  #a2eeef  New feature or request"

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_search_matching_nothing(self, mock_manager_cls: MagicMock) -> None:
        """A search with no matches reports that plainly."""
        mock_manager_cls.return_value = _make_manager(_LABELS)

        result = github_label_list(search="nonexistent")

        assert result == "No labels found."

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_empty_repository_label_set(self, mock_manager_cls: MagicMock) -> None:
        """A repository with no labels reports the same empty message."""
        mock_manager_cls.return_value = _make_manager([])

        result = github_label_list()

        assert result == "No labels found."

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_empty_description_leaves_no_trailing_space(
        self, mock_manager_cls: MagicMock
    ) -> None:
        """A label without a description renders without trailing whitespace."""
        mock_manager_cls.return_value = _make_manager([_label("wontfix", "ffffff")])

        result = github_label_list()

        assert result == "wontfix  #ffffff"

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_exception_is_reported(self, mock_manager_cls: MagicMock) -> None:
        """An arbitrary failure surfaces as an error string."""
        mock_mgr = MagicMock()
        mock_mgr.get_available_labels.side_effect = RuntimeError("boom")
        mock_manager_cls.return_value = mock_mgr

        result = github_label_list()

        assert result == "Error: boom"

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_api_failure_is_not_reported_as_empty(
        self, mock_manager_cls: MagicMock
    ) -> None:
        """A 500 from the API reads as an error, never as 'No labels found.'."""
        mock_mgr = MagicMock()
        mock_mgr.get_available_labels.side_effect = GithubException(
            500, {"message": "Server Error"}, None
        )
        mock_manager_cls.return_value = mock_mgr

        result = github_label_list()

        assert result.startswith("Error:")
        assert "Server Error" in result
        assert "No labels found." not in result
