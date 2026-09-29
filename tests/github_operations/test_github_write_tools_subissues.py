"""Tests for the ``github_subissue_add/_list/_remove`` MCP tools in server.py."""

from pathlib import Path
from typing import Generator, Optional
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from mcp_workspace.github_operations.base_manager import IssueIdentityMismatchError
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.server import (
    github_subissue_add,
    github_subissue_list,
    github_subissue_remove,
    set_project_dir,
)
from mcp_workspace.server_reference_tools import set_reference_projects

_URL = "https://github.com/test/repo/issues/3"
_DUPLICATE = (
    "Issue may not contain duplicate sub-issues and Sub issue may only have one "
    "parent"
)


@pytest.fixture(autouse=True)
def setup_server(project_dir: Path) -> Generator[None, None, None]:
    """Setup the server with the project directory."""
    set_project_dir(project_dir)
    yield


@pytest.fixture
def reference_projects() -> Generator[None, None, None]:
    """Configure a 'sibling' reference project with a GitHub URL."""
    set_reference_projects(
        {
            "sibling": ReferenceProject(
                name="sibling",
                path=Path("/does/not/exist"),
                url="https://github.com/owner/sibling",
            )
        }
    )
    yield
    set_reference_projects({})


def _make_parent(total: Optional[int] = 2) -> MagicMock:
    """Build a mock refetched parent; ``total=None`` means no summary at all."""
    parent = MagicMock()
    parent.html_url = _URL
    parent.sub_issues_summary = None if total is None else MagicMock(total=total)
    return parent


def _make_child(number: int, state: str, title: str) -> MagicMock:
    """Build a mock sub-issue."""
    child = MagicMock()
    child.number = number
    child.state = state
    child.title = title
    return child


class TestSubissueAdd:
    """Tests for github_subissue_add."""

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_success_with_summary(self, mock_cls: MagicMock) -> None:
        """The success line reports the parent URL and sub-issue count."""
        mock_cls.return_value.add_sub_issue.return_value = _make_parent(total=2)

        result = github_subissue_add(parent_number=3, child_number=7)

        assert result == f"Linked #7 as a sub-issue of #3 — {_URL} (2 sub-issues)"
        mock_cls.return_value.add_sub_issue.assert_called_once_with(3, 7)

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_success_without_summary(self, mock_cls: MagicMock) -> None:
        """A missing summary omits the parenthetical instead of inventing 0."""
        mock_cls.return_value.add_sub_issue.return_value = _make_parent(total=None)

        result = github_subissue_add(parent_number=3, child_number=7)

        assert result == f"Linked #7 as a sub-issue of #3 — {_URL}"
        assert "(0 sub-issues)" not in result

    @pytest.mark.parametrize(
        ("parent", "child", "bad"), [(0, 7, 0), (3, -1, -1)], ids=["parent", "child"]
    )
    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_invalid_number(
        self, mock_cls: MagicMock, parent: int, child: int, bad: int
    ) -> None:
        """A non-positive number is rejected before any write."""
        result = github_subissue_add(parent_number=parent, child_number=child)

        assert result == f"Error: invalid issue number: {bad}"
        mock_cls.return_value.add_sub_issue.assert_not_called()

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_self_link(self, mock_cls: MagicMock) -> None:
        """An issue cannot be linked under itself."""
        result = github_subissue_add(parent_number=3, child_number=3)

        assert result == "Error: an issue cannot be its own sub-issue"
        mock_cls.return_value.add_sub_issue.assert_not_called()

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_repository_inaccessible(self, mock_cls: MagicMock) -> None:
        """A None from the mixin renders the repository access error."""
        mock_cls.return_value.add_sub_issue.return_value = None

        result = github_subissue_add(parent_number=3, child_number=7)

        assert result.startswith("Error: Could not access repository")

    @pytest.mark.parametrize(
        ("status", "message"),
        [(422, _DUPLICATE), (404, "Not Found")],
        ids=["duplicate", "not_found"],
    )
    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_github_error_message(
        self, mock_cls: MagicMock, status: int, message: str
    ) -> None:
        """GitHub's message is surfaced verbatim."""
        mock_cls.return_value.add_sub_issue.side_effect = GithubException(
            status, {"message": message}
        )

        result = github_subissue_add(parent_number=3, child_number=7)

        assert result == f"Error: {message}"

    @pytest.mark.parametrize(
        "data", ["plain text body", {"errors": []}], ids=["string", "no_message"]
    )
    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_github_error_without_message(
        self, mock_cls: MagicMock, data: object
    ) -> None:
        """Data that is not a dict with a message falls back to str(exc)."""
        exc = GithubException(500, data)
        mock_cls.return_value.add_sub_issue.side_effect = exc

        result = github_subissue_add(parent_number=3, child_number=7)

        assert result == f"Error: {exc}"

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_pull_request_guard(self, mock_cls: MagicMock) -> None:
        """The mixin's pull-request ValueError is rendered as an error string."""
        mock_cls.return_value.add_sub_issue.side_effect = ValueError(
            "#7 is a pull request, not an issue"
        )

        result = github_subissue_add(parent_number=3, child_number=7)

        assert result == "Error: #7 is a pull request, not an issue"

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_identity_mismatch(self, mock_cls: MagicMock) -> None:
        """A transferred-issue mismatch is rendered, never raised."""
        exc = IssueIdentityMismatchError("issue #7 was transferred")
        mock_cls.return_value.add_sub_issue.side_effect = exc

        result = github_subissue_add(parent_number=3, child_number=7)

        assert result == f"Error: {exc}"

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_error_names_reference_project(
        self,
        mock_cls: MagicMock,
        reference_projects: None,  # pylint: disable=unused-argument
    ) -> None:
        """An error in a reference project names that project."""
        mock_cls.return_value.add_sub_issue.side_effect = GithubException(
            404, {"message": "Not Found"}
        )

        result = github_subissue_add(
            parent_number=3, child_number=7, reference_name="sibling"
        )

        assert result == "Error: Not Found in reference project 'sibling'"

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_unknown_reference_name(self, mock_cls: MagicMock) -> None:
        """An unknown reference name is reported once, without a suffix."""
        result = github_subissue_add(
            parent_number=3, child_number=7, reference_name="nope"
        )

        assert result == "Error: Reference project 'nope' not found"
        mock_cls.assert_not_called()


class TestSubissueRemove:
    """Tests for github_subissue_remove."""

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_success_with_summary(self, mock_cls: MagicMock) -> None:
        """The success line reports the parent URL and sub-issue count."""
        mock_cls.return_value.remove_sub_issue.return_value = _make_parent(total=1)

        result = github_subissue_remove(parent_number=3, child_number=7)

        assert result == f"Unlinked #7 from #3 — {_URL} (1 sub-issues)"
        mock_cls.return_value.remove_sub_issue.assert_called_once_with(3, 7)
        mock_cls.return_value.add_sub_issue.assert_not_called()

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_success_without_summary(self, mock_cls: MagicMock) -> None:
        """A missing summary omits the parenthetical."""
        mock_cls.return_value.remove_sub_issue.return_value = _make_parent(total=None)

        result = github_subissue_remove(parent_number=3, child_number=7)

        assert result == f"Unlinked #7 from #3 — {_URL}"

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_self_link(self, mock_cls: MagicMock) -> None:
        """An issue cannot be unlinked from itself."""
        result = github_subissue_remove(parent_number=3, child_number=3)

        assert result == "Error: an issue cannot be its own sub-issue"
        mock_cls.return_value.remove_sub_issue.assert_not_called()

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_invalid_number(self, mock_cls: MagicMock) -> None:
        """A non-positive number is rejected before any write."""
        result = github_subissue_remove(parent_number=3, child_number=0)

        assert result == "Error: invalid issue number: 0"
        mock_cls.return_value.remove_sub_issue.assert_not_called()

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_unlinked_child_is_an_error(self, mock_cls: MagicMock) -> None:
        """Removing a child that is not linked is an error, not a silent no-op."""
        mock_cls.return_value.remove_sub_issue.side_effect = GithubException(
            404, {"message": "Not Found"}
        )

        result = github_subissue_remove(parent_number=3, child_number=7)

        assert result == "Error: Not Found"


class TestSubissueList:
    """Tests for github_subissue_list."""

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_lists_children_in_order(self, mock_cls: MagicMock) -> None:
        """Each child renders as one line, in API order."""
        mock_cls.return_value.list_sub_issues.return_value = [
            _make_child(7, "open", "First"),
            _make_child(9, "closed", "Second"),
        ]

        result = github_subissue_list(parent_number=3)

        assert result == "#7  open  First\n#9  closed  Second"

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_no_children(self, mock_cls: MagicMock) -> None:
        """An empty list is reported explicitly."""
        mock_cls.return_value.list_sub_issues.return_value = []

        assert github_subissue_list(parent_number=3) == "No sub-issues."

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_repository_inaccessible(self, mock_cls: MagicMock) -> None:
        """A None from the mixin renders the repository access error."""
        mock_cls.return_value.list_sub_issues.return_value = None

        result = github_subissue_list(parent_number=3)

        assert result.startswith("Error: Could not access repository")

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_invalid_number(self, mock_cls: MagicMock) -> None:
        """A non-positive number is rejected before the manager is built."""
        result = github_subissue_list(parent_number=0)

        assert result == "Error: invalid issue number: 0"
        mock_cls.assert_not_called()

    @patch("mcp_workspace.github_operations.issues.IssueManager")
    def test_forwards_max_results(self, mock_cls: MagicMock) -> None:
        """max_results is passed through to the mixin untouched."""
        mock_cls.return_value.list_sub_issues.return_value = []

        github_subissue_list(parent_number=3, max_results=5)

        mock_cls.return_value.list_sub_issues.assert_called_once_with(3, max_results=5)
