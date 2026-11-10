"""Tests for the inline PR review write tools.

Covers ``github_review_comment_reply`` and ``github_review_thread_resolve``
(toolset/github_write.py).
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.reference_projects import ReferenceProject
from tests.conftest import ToolMap


@pytest.fixture
def ref_tools(make_tools: Callable[..., ToolMap]) -> ToolMap:
    """Tools configured with a 'sibling' reference project with a GitHub URL."""
    return make_tools(
        reference_projects={
            "sibling": ReferenceProject(
                name="sibling",
                path=Path("/does/not/exist"),
                url="https://github.com/owner/sibling",
            )
        }
    )


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
    def test_success_message_with_url(
        self, mock_manager_cls: MagicMock, tools: ToolMap
    ) -> None:
        """A successful reply reports the comment ID, PR number, and URL."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.reply_to_review_comment.return_value = _comment_data()

        result = tools["github_review_comment_reply"](
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
    def test_failure_id_zero_is_reported(
        self, mock_manager_cls: MagicMock, tools: ToolMap
    ) -> None:
        """An empty CommentData (id=0) reads as an error, not success."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.reply_to_review_comment.return_value = _EMPTY_COMMENT_DATA

        result = tools["github_review_comment_reply"](
            pr_number=123, comment_id=456, body="Thanks, fixed."
        )

        assert result == ("Error: failed to reply to review comment 456 on PR #123")

    @patch("mcp_workspace.github_operations.pr_manager.PullRequestManager")
    def test_exception_from_manager_is_reported(
        self, mock_manager_cls: MagicMock, tools: ToolMap
    ) -> None:
        """An arbitrary failure from the manager surfaces as an error string."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.reply_to_review_comment.side_effect = RuntimeError("boom")

        result = tools["github_review_comment_reply"](
            pr_number=123, comment_id=456, body="Thanks, fixed."
        )

        assert result == "Error: boom"

    def test_unknown_reference_name(self, tools: ToolMap) -> None:
        """An unknown reference name is reported once, without a suffix."""
        with patch(
            "mcp_workspace.github_operations.pr_manager.PullRequestManager"
        ) as mock_manager_cls:
            result = tools["github_review_comment_reply"](
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
        ref_tools: ToolMap,
    ) -> None:
        """A failure on a reference project's reply names that project."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.reply_to_review_comment.return_value = _EMPTY_COMMENT_DATA

        result = ref_tools["github_review_comment_reply"](
            pr_number=123,
            comment_id=456,
            body="Thanks, fixed.",
            reference_name="sibling",
        )

        assert "sibling" in result
        mock_manager_cls.assert_called_once_with(
            repo_url="https://github.com/owner/sibling"
        )


class TestGithubReviewThreadResolve:
    """Tests for the ``github_review_thread_resolve`` MCP tool."""

    @patch("mcp_workspace.github_operations.pr_manager.PullRequestManager")
    def test_success_message(self, mock_manager_cls: MagicMock, tools: ToolMap) -> None:
        """A successful resolve reports the thread ID and PR number."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.resolve_review_thread.return_value = True

        result = tools["github_review_thread_resolve"](
            pr_number=123, thread_id="thread-abc"
        )

        assert result == "Resolved review thread thread-abc on PR #123"
        manager.resolve_review_thread.assert_called_once_with(123, "thread-abc")

    @patch("mcp_workspace.github_operations.pr_manager.PullRequestManager")
    def test_failure_false_is_reported(
        self, mock_manager_cls: MagicMock, tools: ToolMap
    ) -> None:
        """A False return reads as an error, not success."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.resolve_review_thread.return_value = False

        result = tools["github_review_thread_resolve"](
            pr_number=123, thread_id="thread-abc"
        )

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
        self, mock_manager_cls: MagicMock, message: str, tools: ToolMap
    ) -> None:
        """Each of the three ValueError reasons surfaces as an error string."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.resolve_review_thread.side_effect = ValueError(message)

        result = tools["github_review_thread_resolve"](
            pr_number=123, thread_id="thread-abc"
        )

        assert result == f"Error: {message}"

    def test_unknown_reference_name(self, tools: ToolMap) -> None:
        """An unknown reference name is reported once, without a suffix."""
        with patch(
            "mcp_workspace.github_operations.pr_manager.PullRequestManager"
        ) as mock_manager_cls:
            result = tools["github_review_thread_resolve"](
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
        ref_tools: ToolMap,
    ) -> None:
        """A failure on a reference project's resolve names that project."""
        manager: MagicMock = mock_manager_cls.return_value
        manager.resolve_review_thread.return_value = False

        result = ref_tools["github_review_thread_resolve"](
            pr_number=123,
            thread_id="thread-abc",
            reference_name="sibling",
        )

        assert "sibling" in result
        mock_manager_cls.assert_called_once_with(
            repo_url="https://github.com/owner/sibling"
        )
