"""Tests for the label and pull-request MCP tools in server.py.

Covers ``github_label_list`` and ``github_pr_create``.
"""

from pathlib import Path
from typing import Any, Callable, Generator, Optional
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from mcp_workspace.github_operations.pr_manager import PullRequestManager
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.server import (
    github_label_list,
    github_pr_create,
    github_review_comment_reply,
    github_review_thread_resolve,
    set_project_dir,
)
from mcp_workspace.server_reference_tools import set_reference_projects

# Bound at import time, before any @patch is active: patching
# ``mcp_workspace.github_operations.pr_manager.PullRequestManager`` replaces the
# module attribute, so an import inside a patched test body would hand back the
# MagicMock and the real branch rules would never run.
_REAL_VALIDATE_BRANCH_NAME: Callable[[Any, str], bool] = (
    PullRequestManager._validate_branch_name  # pylint: disable=protected-access
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


# =============================================================================
# github_pr_create tests
# =============================================================================


def _pr_data(number: int = 7) -> dict[str, Any]:
    """Create a PullRequestData-shaped dict for testing."""
    return {
        "number": number,
        "title": "Add feature",
        "url": f"https://github.com/test/repo/pull/{number}",
    }


def _wire_manager(
    mock_manager_cls: MagicMock,
    pr: Optional[dict[str, Any]] = None,
) -> MagicMock:
    """Wire a mocked PullRequestManager with the library's real branch rules.

    The patched manager would otherwise return a truthy MagicMock from
    ``_validate_branch_name``, making every branch name pass.
    """
    manager: MagicMock = mock_manager_cls.return_value
    # pylint: disable-next=protected-access
    manager._validate_branch_name.side_effect = lambda name: _REAL_VALIDATE_BRANCH_NAME(
        None, name
    )
    manager.create_pull_request.return_value = _pr_data() if pr is None else pr
    return manager


@patch("mcp_workspace.server._resolve_base_branch")
@patch("mcp_workspace.git_operations.get_current_branch_name")
@patch("mcp_workspace.github_operations.pr_manager.PullRequestManager")
class TestGithubPrCreate:
    """Tests for the ``github_pr_create`` MCP tool."""

    @pytest.fixture(autouse=True)
    def origin_has_base(self) -> Generator[MagicMock, None, None]:
        """Every resolved base exists on origin unless a test says otherwise."""
        with patch(
            "mcp_workspace.git_operations.probe_origin_branch",
            return_value={
                "success": True,
                "error": None,
                "returncode": 0,
                "stderr": None,
                "exists": True,
            },
        ) as mock_origin:
            yield mock_origin

    def test_creates_pull_request(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """A valid request reports the new PR number and URL."""
        mock_current.return_value = "feature/x"
        mock_resolve.return_value = ("main", None)
        manager = _wire_manager(mock_manager_cls)

        result = github_pr_create(title="Add feature", body="Body text")

        assert result == "Created PR #7 — https://github.com/test/repo/pull/7"
        manager.create_pull_request.assert_called_once_with(
            title="Add feature",
            head_branch="feature/x",
            base_branch="main",
            body="Body text",
        )

    def test_head_omitted_uses_current_branch(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Without ``head`` the current branch is resolved and used."""
        mock_current.return_value = "feature/x"
        mock_resolve.return_value = ("main", None)
        manager = _wire_manager(mock_manager_cls)

        github_pr_create(title="Add feature", base="develop")

        mock_current.assert_called_once()
        assert (
            manager.create_pull_request.call_args.kwargs["head_branch"] == "feature/x"
        )

    def test_base_omitted_is_resolved_for_head(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Without ``base`` the base is resolved for ``head`` and used."""
        mock_current.return_value = "feature/x"
        mock_resolve.return_value = ("main", None)
        manager = _wire_manager(mock_manager_cls)

        github_pr_create(title="Add feature", head="feature/y")

        mock_resolve.assert_called_once()
        assert mock_resolve.call_args.args[1] == "feature/y"
        assert manager.create_pull_request.call_args.kwargs["base_branch"] == "main"

    def test_both_branches_supplied_skips_resolvers(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Explicit branches are used verbatim; neither resolver is called."""
        manager = _wire_manager(mock_manager_cls)

        result = github_pr_create(title="Add feature", head="feature/y", base="develop")

        assert result.startswith("Created PR #7")
        mock_current.assert_not_called()
        mock_resolve.assert_not_called()
        manager.create_pull_request.assert_called_once_with(
            title="Add feature",
            head_branch="feature/y",
            base_branch="develop",
            body="",
        )

    @pytest.mark.parametrize("title", ["", "   "])
    def test_empty_title_is_rejected(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
        title: str,
    ) -> None:
        """An empty or whitespace-only title errors without writing."""
        manager = _wire_manager(mock_manager_cls)

        result = github_pr_create(title=title)

        assert result.startswith("Error:")
        manager.create_pull_request.assert_not_called()

    def test_head_equal_to_base_is_rejected(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """A PR from a branch to itself errors and names the branch."""
        mock_current.return_value = "main"
        mock_resolve.return_value = ("main", None)
        manager = _wire_manager(mock_manager_cls)

        result = github_pr_create(title="Add feature")

        assert result.startswith("Error:")
        assert "main" in result
        manager.create_pull_request.assert_not_called()

    def test_invalid_branch_name_is_rejected(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """The library validator rejects a bad branch name before any write."""
        manager = _wire_manager(mock_manager_cls)

        result = github_pr_create(title="Add feature", head="feat~1", base="main")

        assert result.startswith("Error:")
        assert "feat~1" in result
        # pylint: disable-next=protected-access
        manager._validate_branch_name.assert_any_call("feat~1")
        manager.create_pull_request.assert_not_called()

    def test_invalid_base_branch_name_is_rejected(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """The same validator also guards the base branch."""
        manager = _wire_manager(mock_manager_cls)

        result = github_pr_create(
            title="Add feature", head="feature/y", base="bad.lock"
        )

        assert result.startswith("Error:")
        assert "bad.lock" in result
        # pylint: disable-next=protected-access
        manager._validate_branch_name.assert_any_call("bad.lock")
        manager.create_pull_request.assert_not_called()

    def test_valid_branch_names_pass_the_real_validator(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Ordinary branch names survive the real rules, so the guard is not blanket."""
        manager = _wire_manager(mock_manager_cls)

        result = github_pr_create(
            title="Add feature", head="feature/232-write-tools", base="main"
        )

        assert result.startswith("Created PR #7")
        # pylint: disable-next=protected-access
        manager._validate_branch_name.assert_any_call("feature/232-write-tools")

    def test_unresolvable_current_branch(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """An unresolvable current branch errors instead of guessing."""
        mock_current.return_value = None
        mock_resolve.return_value = ("main", None)
        manager = _wire_manager(mock_manager_cls)

        result = github_pr_create(title="Add feature")

        assert result.startswith("Error:")
        manager.create_pull_request.assert_not_called()

    def test_unresolvable_base_branch(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """An unresolvable base branch errors instead of assuming 'main'."""
        mock_current.return_value = "feature/x"
        mock_resolve.return_value = (None, None)
        manager = _wire_manager(mock_manager_cls)

        result = github_pr_create(title="Add feature")

        assert result.startswith("Error:")
        manager.create_pull_request.assert_not_called()

    def test_empty_result_is_not_reported_as_success(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """The library's empty-dict failure sentinel reads as an error."""
        mock_current.return_value = "feature/x"
        mock_resolve.return_value = ("main", None)
        _wire_manager(mock_manager_cls, pr={})

        result = github_pr_create(title="Add feature")

        assert result.startswith("Error:")
        assert "Created PR" not in result

    def test_manager_construction_failure_is_reported(
        self,
        mock_manager_cls: MagicMock,
        mock_current: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """A ValueError from the manager constructor surfaces as an error string."""
        mock_manager_cls.side_effect = ValueError("project_dir is required")

        result = github_pr_create(title="Add feature")

        assert result == "Error: project_dir is required"


# =============================================================================
# github_review_comment_reply tests
# =============================================================================


def _comment_data(comment_id: int = 456) -> dict[str, Any]:
    """Create a CommentData-shaped dict for testing."""
    return {
        "id": comment_id,
        "body": "Thanks, fixed.",
        "user": "testuser",
        "created_at": "2023-01-01T00:00:00Z",
        "updated_at": "2023-01-01T00:00:00Z",
        "url": f"https://github.com/test/repo/pull/123#discussion_r{comment_id}",
    }


_EMPTY_COMMENT_DATA: dict[str, Any] = {
    "id": 0,
    "body": "",
    "user": None,
    "created_at": None,
    "updated_at": None,
    "url": "",
}


class TestGithubReviewCommentReply:
    """Tests for the ``github_review_comment_reply`` MCP tool."""

    @patch("mcp_workspace.github_operations.pr_manager.PullRequestManager")
    def test_success_message_with_url(self, mock_manager_cls: MagicMock) -> None:
        """A successful reply reports the comment ID, PR number, and URL."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.reply_to_review_comment.return_value = _comment_data()

        result = github_review_comment_reply(
            pr_number=123, comment_id=456, body="Thanks, fixed."
        )

        assert result == (
            "Replied to review comment 456 on PR #123 — "
            "https://github.com/test/repo/pull/123#discussion_r456"
        )
        manager.reply_to_review_comment.assert_called_once_with(
            123, 456, "Thanks, fixed."
        )

    @patch("mcp_workspace.github_operations.pr_manager.PullRequestManager")
    def test_failure_id_zero_is_reported(self, mock_manager_cls: MagicMock) -> None:
        """An empty CommentData (id=0) reads as an error, not success."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.reply_to_review_comment.return_value = _EMPTY_COMMENT_DATA

        result = github_review_comment_reply(
            pr_number=123, comment_id=456, body="Thanks, fixed."
        )

        assert result == ("Error: failed to reply to review comment 456 on PR #123")

    @patch("mcp_workspace.github_operations.pr_manager.PullRequestManager")
    def test_exception_from_manager_is_reported(
        self, mock_manager_cls: MagicMock
    ) -> None:
        """An arbitrary failure from the manager surfaces as an error string."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.reply_to_review_comment.side_effect = RuntimeError("boom")

        result = github_review_comment_reply(
            pr_number=123, comment_id=456, body="Thanks, fixed."
        )

        assert result == "Error: boom"

    def test_unknown_reference_name(self) -> None:
        """An unknown reference name is reported once, without a suffix."""
        with patch(
            "mcp_workspace.github_operations.pr_manager.PullRequestManager"
        ) as mock_manager_cls:
            result = github_review_comment_reply(
                pr_number=123,
                comment_id=456,
                body="Thanks, fixed.",
                reference_name="nope",
            )

            assert result == "Error: Reference project 'nope' not found"
            mock_manager_cls.assert_not_called()

    @patch("mcp_workspace.github_operations.pr_manager.PullRequestManager")
    def test_reference_project_failure_names_project(
        self,
        mock_manager_cls: MagicMock,
        reference_projects: None,  # pylint: disable=unused-argument
    ) -> None:
        """A failure on a reference project's reply names that project."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.reply_to_review_comment.return_value = _EMPTY_COMMENT_DATA

        result = github_review_comment_reply(
            pr_number=123,
            comment_id=456,
            body="Thanks, fixed.",
            reference_name="sibling",
        )

        assert "sibling" in result
        mock_manager_cls.assert_called_once_with(
            repo_url="https://github.com/owner/sibling"
        )


# =============================================================================
# github_review_thread_resolve tests
# =============================================================================


class TestGithubReviewThreadResolve:
    """Tests for the ``github_review_thread_resolve`` MCP tool."""

    @patch("mcp_workspace.github_operations.pr_manager.PullRequestManager")
    def test_success_message(self, mock_manager_cls: MagicMock) -> None:
        """A successful resolve reports the thread ID and PR number."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.resolve_review_thread.return_value = True

        result = github_review_thread_resolve(pr_number=123, thread_id="thread-abc")

        assert result == "Resolved review thread thread-abc on PR #123"
        manager.resolve_review_thread.assert_called_once_with(123, "thread-abc")

    @patch("mcp_workspace.github_operations.pr_manager.PullRequestManager")
    def test_failure_false_is_reported(self, mock_manager_cls: MagicMock) -> None:
        """A False return reads as an error, not success."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.resolve_review_thread.return_value = False

        result = github_review_thread_resolve(pr_number=123, thread_id="thread-abc")

        assert result == (
            "Error: failed to resolve review thread thread-abc on PR #123"
        )

    @pytest.mark.parametrize(
        "message",
        [
            "Review thread thread-abc not found",
            "Review thread thread-abc does not belong to PR #123",
            "Review thread thread-abc is already resolved",
        ],
    )
    @patch("mcp_workspace.github_operations.pr_manager.PullRequestManager")
    def test_value_error_from_manager_is_reported(
        self, mock_manager_cls: MagicMock, message: str
    ) -> None:
        """Each of the three ValueError reasons surfaces as an error string."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.resolve_review_thread.side_effect = ValueError(message)

        result = github_review_thread_resolve(pr_number=123, thread_id="thread-abc")

        assert result == f"Error: {message}"

    def test_unknown_reference_name(self) -> None:
        """An unknown reference name is reported once, without a suffix."""
        with patch(
            "mcp_workspace.github_operations.pr_manager.PullRequestManager"
        ) as mock_manager_cls:
            result = github_review_thread_resolve(
                pr_number=123,
                thread_id="thread-abc",
                reference_name="nope",
            )

            assert result == "Error: Reference project 'nope' not found"
            mock_manager_cls.assert_not_called()

    @patch("mcp_workspace.github_operations.pr_manager.PullRequestManager")
    def test_reference_project_failure_names_project(
        self,
        mock_manager_cls: MagicMock,
        reference_projects: None,  # pylint: disable=unused-argument
    ) -> None:
        """A failure on a reference project's resolve names that project."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.resolve_review_thread.return_value = False

        result = github_review_thread_resolve(
            pr_number=123,
            thread_id="thread-abc",
            reference_name="sibling",
        )

        assert "sibling" in result
        mock_manager_cls.assert_called_once_with(
            repo_url="https://github.com/owner/sibling"
        )
