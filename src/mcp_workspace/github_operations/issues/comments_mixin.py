"""Comments mixin for IssueManager.

This module provides the CommentsMixin class containing comment-related operations
for GitHub issues.
"""

from __future__ import annotations

import logging
from typing import List

from mcp_coder_utils.log_utils import log_function_call

from ..base_manager import BaseGitHubManager, _handle_github_errors
from .base import validate_comment_id, validate_issue_number
from .types import CommentData

logger = logging.getLogger(__name__)

__all__ = ["CommentsMixin"]


class CommentsMixin:
    """Mixin providing issue comment operations.

    This mixin is designed to be used with BaseGitHubManager.
    """

    @log_function_call
    @_handle_github_errors(
        default_return=CommentData(
            id=0,
            body="",
            user=None,
            created_at=None,
            updated_at=None,
            url="",
        )
    )
    def add_comment(
        self: "BaseGitHubManager", issue_number: int, body: str
    ) -> CommentData:
        """Add a comment to an issue.

        Args:
            issue_number: Issue number to add comment to
            body: Comment text (required, cannot be empty)

        Returns:
            CommentData with created comment information, or empty dict when
            the repository is unavailable

        Raises:
            ValueError: If issue number is invalid or body is empty
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Example:
            >>> comment = manager.add_comment(123, "This is a test comment")
            >>> print(f"Created comment {comment['id']}")
        """  # noqa: DOC502  # IssueIdentityMismatchError comes from _get_issue_checked
        # Validate issue number
        validate_issue_number(issue_number)

        # Validate body
        if not body or not body.strip():
            raise ValueError("Comment body cannot be empty")

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return CommentData(
                id=0,
                body="",
                user=None,
                created_at=None,
                updated_at=None,
                url="",
            )

        # Get issue and create comment
        github_issue = self._get_issue_checked(repo, issue_number)
        github_comment = github_issue.create_comment(body.strip())

        # Convert to CommentData
        return CommentData(
            id=github_comment.id,
            body=github_comment.body or "",
            user=github_comment.user.login if github_comment.user else None,
            created_at=(
                github_comment.created_at.isoformat()
                if github_comment.created_at
                else None
            ),
            updated_at=(
                github_comment.updated_at.isoformat()
                if github_comment.updated_at
                else None
            ),
            url=github_comment.html_url,
        )

    @log_function_call
    @_handle_github_errors(default_return=[])
    def get_comments(self: "BaseGitHubManager", issue_number: int) -> List[CommentData]:
        """Get all comments on an issue.

        Args:
            issue_number: Issue number to get comments from

        Returns:
            List of CommentData dictionaries with comment information, or empty
            list when the repository is unavailable

        Raises:
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Example:
            >>> comments = manager.get_comments(123)
            >>> for comment in comments:
            ...     print(f"{comment['user']}: {comment['body']}")
        """  # noqa: DOC502  # IssueIdentityMismatchError comes from _get_issue_checked
        # Validate issue number
        validate_issue_number(issue_number)

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return []

        # Get issue and comments
        github_issue = self._get_issue_checked(repo, issue_number)
        github_comments = github_issue.get_comments()

        # Convert to CommentData list
        comments: List[CommentData] = []
        for comment in github_comments:
            comments.append(
                CommentData(
                    id=comment.id,
                    body=comment.body or "",
                    user=comment.user.login if comment.user else None,
                    created_at=(
                        comment.created_at.isoformat() if comment.created_at else None
                    ),
                    updated_at=(
                        comment.updated_at.isoformat() if comment.updated_at else None
                    ),
                    url=comment.html_url,
                )
            )

        return comments

    @log_function_call
    @_handle_github_errors(
        default_return=CommentData(
            id=0,
            body="",
            user=None,
            created_at=None,
            updated_at=None,
            url="",
        )
    )
    def edit_comment(
        self: "BaseGitHubManager", issue_number: int, comment_id: int, body: str
    ) -> CommentData:
        """Edit an existing comment on an issue.

        Args:
            issue_number: Issue number containing the comment
            comment_id: Comment ID to edit
            body: New comment text (required, cannot be empty)

        Returns:
            CommentData with updated comment information, or empty dict when
            the repository is unavailable

        Raises:
            ValueError: If issue number is invalid, comment ID is invalid, or body is empty
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Example:
            >>> comment = manager.edit_comment(123, 456789, "Updated comment text")
            >>> print(f"Updated comment {comment['id']}")
        """  # noqa: DOC502  # IssueIdentityMismatchError comes from _get_issue_checked
        # Validate issue number
        validate_issue_number(issue_number)

        # Validate comment ID
        validate_comment_id(comment_id)

        # Validate body
        if not body or not body.strip():
            raise ValueError("Comment body cannot be empty")

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return CommentData(
                id=0,
                body="",
                user=None,
                created_at=None,
                updated_at=None,
                url="",
            )

        # Get issue to verify it exists
        github_issue = self._get_issue_checked(repo, issue_number)

        # Get the comment directly from repository
        github_comment = github_issue.get_comment(comment_id)

        # Edit the comment
        github_comment.edit(body.strip())

        # Get fresh comment data after editing
        github_comment = github_issue.get_comment(comment_id)

        # Convert to CommentData
        return CommentData(
            id=github_comment.id,
            body=github_comment.body or "",
            user=github_comment.user.login if github_comment.user else None,
            created_at=(
                github_comment.created_at.isoformat()
                if github_comment.created_at
                else None
            ),
            updated_at=(
                github_comment.updated_at.isoformat()
                if github_comment.updated_at
                else None
            ),
            url=github_comment.html_url,
        )

    @log_function_call
    @_handle_github_errors(default_return=False)
    def delete_comment(
        self: "BaseGitHubManager", issue_number: int, comment_id: int
    ) -> bool:
        """Delete a comment from an issue.

        Args:
            issue_number: Issue number containing the comment
            comment_id: Comment ID to delete

        Returns:
            True if deletion was successful, False otherwise

        Raises:
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Example:
            >>> success = manager.delete_comment(123, 456789)
            >>> print(f"Deletion {'successful' if success else 'failed'}")
        """  # noqa: DOC502  # IssueIdentityMismatchError comes from _get_issue_checked
        # Validate issue number
        validate_issue_number(issue_number)

        # Validate comment ID
        validate_comment_id(comment_id)

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return False

        # Get issue to verify it exists
        github_issue = self._get_issue_checked(repo, issue_number)

        # Get the comment directly from repository
        github_comment = github_issue.get_comment(comment_id)

        # Delete the comment
        github_comment.delete()

        return True
