"""Labels mixin for IssueManager.

This module provides the LabelsMixin class containing pure label operations
for managing issue labels through the GitHub API.
"""

from __future__ import annotations

import logging
from typing import Iterable, List

from mcp_coder_utils.log_utils import log_function_call

from ..base_manager import BaseGitHubManager, _handle_github_errors
from ..labels_manager import LabelData
from .base import validate_issue_number
from .types import IssueData, create_empty_issue_data

logger = logging.getLogger(__name__)

__all__ = ["LabelsMixin"]


class LabelsMixin:
    """Mixin providing issue label operations.

    This mixin is designed to be used with BaseGitHubManager.
    Contains pure label operations (get, add, remove, transition).
    """

    @log_function_call
    @_handle_github_errors(default_return=[])
    def get_available_labels(self: "BaseGitHubManager") -> List[LabelData]:
        """Get all available labels in the repository.

        Returns:
            List of LabelData dictionaries with label information, or empty list on error

        Example:
            >>> labels = manager.get_available_labels()
            >>> for label in labels:
            ...     print(f"{label['name']}: {label['color']}")
        """
        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return []

        # Get all labels from repository
        github_labels = repo.get_labels()

        # Convert to LabelData list
        labels: List[LabelData] = []
        for label in github_labels:
            labels.append(
                LabelData(
                    name=label.name,
                    color=label.color,
                    description=label.description or "",
                    url=label.url,
                )
            )

        return labels

    @log_function_call
    @_handle_github_errors(default_return=create_empty_issue_data())
    def add_labels(
        self: "BaseGitHubManager", issue_number: int, *labels: str
    ) -> IssueData:
        """Add labels to an issue.

        Args:
            issue_number: Issue number to add labels to
            *labels: Variable number of label names to add

        Returns:
            IssueData with updated issue information, or empty IssueData when
            the repository is unavailable

        Raises:
            ValueError: If issue number is invalid or no labels provided
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Example:
            >>> updated_issue = manager.add_labels(123, "bug", "high-priority")
            >>> print(f"Labels: {updated_issue['labels']}")
        """
        # Validate issue number
        validate_issue_number(issue_number)

        # Validate labels
        if not labels:
            raise ValueError("At least one label must be provided")

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return create_empty_issue_data()

        # Get issue and add labels
        github_issue = self._get_issue_checked(repo, issue_number)
        github_issue.add_to_labels(*labels)

        # Get fresh issue data after adding labels
        github_issue = self._get_issue_checked(repo, issue_number)

        # Convert to IssueData
        return IssueData(
            number=github_issue.number,
            title=github_issue.title,
            body=github_issue.body or "",
            state=github_issue.state,
            labels=[label.name for label in github_issue.labels],
            assignees=[assignee.login for assignee in github_issue.assignees],
            user=github_issue.user.login if github_issue.user else None,
            created_at=(
                github_issue.created_at.isoformat() if github_issue.created_at else None
            ),
            updated_at=(
                github_issue.updated_at.isoformat() if github_issue.updated_at else None
            ),
            url=github_issue.html_url,
            locked=github_issue.locked,
        )

    @log_function_call
    @_handle_github_errors(default_return=create_empty_issue_data())
    def remove_labels(
        self: "BaseGitHubManager", issue_number: int, *labels: str
    ) -> IssueData:
        """Remove labels from an issue.

        Args:
            issue_number: Issue number to remove labels from
            *labels: Variable number of label names to remove

        Returns:
            IssueData with updated issue information, or empty IssueData when
            the repository is unavailable

        Raises:
            ValueError: If issue number is invalid or no labels provided
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Example:
            >>> updated_issue = manager.remove_labels(123, "bug", "high-priority")
            >>> print(f"Labels: {updated_issue['labels']}")
        """
        # Validate issue number
        validate_issue_number(issue_number)

        # Validate labels
        if not labels:
            raise ValueError("At least one label must be provided")

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return create_empty_issue_data()

        # Get issue and remove labels
        github_issue = self._get_issue_checked(repo, issue_number)
        github_issue.remove_from_labels(*labels)

        # Get fresh issue data after removing labels
        github_issue = self._get_issue_checked(repo, issue_number)

        # Convert to IssueData
        return IssueData(
            number=github_issue.number,
            title=github_issue.title,
            body=github_issue.body or "",
            state=github_issue.state,
            labels=[label.name for label in github_issue.labels],
            assignees=[assignee.login for assignee in github_issue.assignees],
            user=github_issue.user.login if github_issue.user else None,
            created_at=(
                github_issue.created_at.isoformat() if github_issue.created_at else None
            ),
            updated_at=(
                github_issue.updated_at.isoformat() if github_issue.updated_at else None
            ),
            url=github_issue.html_url,
            locked=github_issue.locked,
        )

    @log_function_call
    @_handle_github_errors(default_return=create_empty_issue_data())
    def set_labels(
        self: "BaseGitHubManager", issue_number: int, *labels: str
    ) -> IssueData:
        """Set labels on an issue, replacing all existing labels.

        Args:
            issue_number: Issue number to set labels on
            *labels: Variable number of label names to set (can be empty to remove all)

        Returns:
            IssueData with updated issue information, or empty IssueData when
            the repository is unavailable

        Raises:
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Example:
            >>> updated_issue = manager.set_labels(123, "bug", "high-priority")
            >>> print(f"Labels: {updated_issue['labels']}")
            >>> # Remove all labels
            >>> updated_issue = manager.set_labels(123)
            >>> print(f"Labels: {updated_issue['labels']}")  # Empty list
        """
        # Validate issue number
        validate_issue_number(issue_number)

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return create_empty_issue_data()

        # Get issue and set labels (replaces all existing labels)
        github_issue = self._get_issue_checked(repo, issue_number)
        github_issue.set_labels(*labels)

        # Get fresh issue data after setting labels
        github_issue = self._get_issue_checked(repo, issue_number)

        # Convert to IssueData
        return IssueData(
            number=github_issue.number,
            title=github_issue.title,
            body=github_issue.body or "",
            state=github_issue.state,
            labels=[label.name for label in github_issue.labels],
            assignees=[assignee.login for assignee in github_issue.assignees],
            user=github_issue.user.login if github_issue.user else None,
            created_at=(
                github_issue.created_at.isoformat() if github_issue.created_at else None
            ),
            updated_at=(
                github_issue.updated_at.isoformat() if github_issue.updated_at else None
            ),
            url=github_issue.html_url,
            locked=github_issue.locked,
        )

    @log_function_call
    @_handle_github_errors(default_return=False)
    def transition_issue_label(
        self: "BaseGitHubManager",
        issue_number: int,
        new_label: str,
        labels_to_clear: Iterable[str] = (),
    ) -> bool:
        """Atomic label transition primitive — no workflow semantics.

        Computes ``(current - labels_to_clear) | {new_label}`` and applies the
        result via :meth:`set_labels`. Idempotent: if ``new_label`` is already
        present AND there is no overlap between current labels and
        ``labels_to_clear``, returns ``True`` without calling ``set_labels``.

        Args:
            issue_number: Issue number to operate on.
            new_label: Label to ensure is present on the issue.
            labels_to_clear: Iterable of labels to remove if present.

        Returns:
            ``True`` on success (including idempotent no-op), ``False`` on
            swallowed error or failed ``set_labels``.

        Raises:
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different
                number. Propagates from :meth:`get_issue` / :meth:`set_labels`,
                so the ``bool`` contract does not hold on that path.
        """
        # Validate issue number (decorator re-raises ValueError).
        validate_issue_number(issue_number)

        # Fetch current labels. get_issue has its own default_return that
        # yields an empty IssueData (number=0) on swallowed failure.
        issue = self.get_issue(issue_number)  # type: ignore[attr-defined]
        if issue["number"] == 0:
            return False

        current = set(issue["labels"])
        to_clear = set(labels_to_clear)

        # Idempotent short-circuit: target present and no overlap to clear.
        if new_label in current and not (to_clear & current):
            return True

        new_labels = (current - to_clear) | {new_label}
        result = self.set_labels(issue_number, *new_labels)  # type: ignore[attr-defined]
        return bool(result["number"] != 0)
