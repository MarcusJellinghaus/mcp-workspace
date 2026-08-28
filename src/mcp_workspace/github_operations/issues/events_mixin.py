"""Events mixin for IssueManager.

This module provides the EventsMixin class containing event-related operations
for GitHub issues.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from github.GithubException import GithubException
from mcp_coder_utils.log_utils import log_function_call

from ..base_manager import BaseGitHubManager
from .base import validate_issue_number
from .types import EventData, IssueEventType

logger = logging.getLogger(__name__)

__all__ = ["EventsMixin"]


class EventsMixin:
    """Mixin providing issue event operations.

    This mixin is designed to be used with BaseGitHubManager.
    """

    @log_function_call
    def get_issue_events(
        self: "BaseGitHubManager",
        issue_number: int,
        event_type: Optional[IssueEventType] = None,
    ) -> List[EventData]:
        """Get timeline events for an issue.

        Args:
            issue_number: Issue number to get events for
            event_type: Optional event type to filter by (e.g., IssueEventType.LABELED)
                       If None, returns all event types

        Returns:
            List of EventData dicts with event information

        Raises:
            GithubException: For authentication, permission, or API errors
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Note:
            Returns ALL event types by default. Currently, the validation workflow
            only uses label events (labeled/unlabeled), but other event types are
            available for future use.

        Example:
            >>> # Get all events
            >>> events = manager.get_issue_events(123)
            >>> # Get only labeled events
            >>> labeled = manager.get_issue_events(123, IssueEventType.LABELED)
            >>> for event in labeled:
            ...     print(f"Label '{event['label']}' added at {event['created_at']}")
        """
        # Validate issue number
        validate_issue_number(issue_number)

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return []

        # Get issue
        try:
            github_issue = self._get_issue_checked(repo, issue_number)
        except GithubException as e:
            logger.error(f"Failed to get issue #{issue_number}: {e}")
            raise

        # Get events
        try:
            github_events = github_issue.get_events()
        except GithubException as e:
            logger.error(f"Failed to get events for issue #{issue_number}: {e}")
            raise

        # Convert to EventData list
        events: List[EventData] = []
        for event in github_events:
            # Skip if event_type is provided and doesn't match
            if event_type is not None and event.event != event_type.value:
                continue

            # Extract label name for labeled/unlabeled events
            label_name = None
            if event.event in ["labeled", "unlabeled"] and hasattr(event, "label"):
                label_name = event.label.name if event.label else None

            # Extract actor username
            actor_username = None
            if hasattr(event, "actor") and event.actor:
                actor_username = event.actor.login

            # Format timestamp to ISO string
            created_at = event.created_at.isoformat() if event.created_at else ""

            # Create EventData
            events.append(
                EventData(
                    event=event.event,
                    label=label_name,
                    created_at=created_at,
                    actor=actor_username,
                )
            )

        return events
