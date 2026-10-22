"""PR review comment mixin for PullRequestManager.

This module provides the PRReviewMixin class containing inline review-comment
reply and thread-resolution operations for GitHub pull requests.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mcp_coder_utils.log_utils import log_function_call

from .base_manager import _handle_github_errors
from .issues.types import CommentData
from .trust import normalize_author_association

if TYPE_CHECKING:
    from .pr_manager import PullRequestManager

logger = logging.getLogger(__name__)

__all__ = ["PRReviewMixin"]


def _empty_comment_data() -> CommentData:
    """Return a fresh empty CommentData for the decorator default (id=0)."""
    return CommentData(
        id=0,
        body="",
        user=None,
        created_at=None,
        updated_at=None,
        url="",
        author_association=None,
    )


class PRReviewMixin:
    """Mixin providing inline PR review-comment reply and resolve operations.

    This mixin is designed to be used with PullRequestManager, which supplies
    _validate_pr_number, _get_repository, and _github_client.
    """

    def _validate_comment_id(self, comment_id: int) -> bool:
        """Validate review comment ID.

        Args:
            comment_id: Comment ID to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(comment_id, int) or comment_id <= 0:
            logger.error(
                f"Invalid comment ID: {comment_id}. Must be a positive integer."
            )
            return False
        return True

    @log_function_call
    @_handle_github_errors(default_return=_empty_comment_data)
    def reply_to_review_comment(
        self: "PullRequestManager", pr_number: int, comment_id: int, body: str
    ) -> CommentData:
        """Reply to an inline PR review comment.

        Wraps PyGithub's PullRequest.create_review_comment_reply(). No PR/comment
        cross-check: GitHub's REST endpoint is nested under pull_number, so a
        comment_id from another PR is rejected by GitHub itself.

        Args:
            pr_number: Pull request number the review comment belongs to
            comment_id: Review comment ID to reply to
            body: Reply text (required, cannot be empty)

        Returns:
            CommentData with the created reply's information, or empty
            CommentData (id=0) on failure.
        """
        if not self._validate_pr_number(pr_number):
            return _empty_comment_data()

        if not self._validate_comment_id(comment_id):
            return _empty_comment_data()

        if not body or not body.strip():
            logger.error("Reply body cannot be empty")
            return _empty_comment_data()

        repo = self._get_repository()
        if repo is None:
            return _empty_comment_data()

        pr = repo.get_pull(pr_number)
        reply = pr.create_review_comment_reply(comment_id, body.strip())

        return CommentData(
            id=reply.id,
            body=reply.body or "",
            user=reply.user.login if reply.user else None,
            created_at=(reply.created_at.isoformat() if reply.created_at else None),
            updated_at=(reply.updated_at.isoformat() if reply.updated_at else None),
            url=reply.html_url,
            author_association=normalize_author_association(reply.author_association),
        )

    @log_function_call
    @_handle_github_errors(default_return=False)
    def resolve_review_thread(
        self: "PullRequestManager", pr_number: int, thread_id: str
    ) -> bool:
        """Resolve a PR review thread via the resolveReviewThread GraphQL mutation.

        Confirms thread_id belongs to pr_number with a single targeted
        node(id:) lookup before resolving — the mutation itself only takes
        threadId and does not check it against a PR.

        Args:
            pr_number: Pull request number the review thread must belong to
            thread_id: GraphQL node ID of the review thread to resolve

        Returns:
            True on success. False only for invalid pr_number or an
            unavailable repository. Not-found / wrong-PR / already-resolved
            raise ValueError instead, since those need a message
            distinguishing the three failure modes.

        Raises:
            ValueError: If thread_id is not a non-empty string, the thread is
                not found, belongs to a different PR, or is already resolved.
        """
        if not self._validate_pr_number(pr_number):
            return False

        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("thread_id must be a non-empty string")

        repo = self._get_repository()
        if repo is None:
            return False

        requester = self._github_client._Github__requester  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub

        lookup_query = """
        query($id: ID!) {
          node(id: $id) {
            ... on PullRequestReviewThread {
              isResolved
              pullRequest {
                number
              }
            }
          }
        }
        """
        _, lookup_result = requester.graphql_query(
            query=lookup_query, variables={"id": thread_id}
        )
        node = (lookup_result.get("data") or {}).get("node")
        if node is None:
            raise ValueError(f"Review thread {thread_id} not found")
        if (node.get("pullRequest") or {}).get("number") != pr_number:
            raise ValueError(
                f"Review thread {thread_id} does not belong to PR #{pr_number}"
            )
        if node.get("isResolved"):
            raise ValueError(f"Review thread {thread_id} is already resolved")

        mutation = """
        mutation($id: ID!) {
          resolveReviewThread(input: {threadId: $id}) {
            thread {
              isResolved
            }
          }
        }
        """
        requester.graphql_query(query=mutation, variables={"id": thread_id})
        return True
