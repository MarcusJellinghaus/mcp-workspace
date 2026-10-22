"""Type definitions for GitHub issue operations.

This module contains TypedDict and Enum definitions used across the issues subpackage.
"""

from enum import Enum
from typing import TYPE_CHECKING, List, NotRequired, Optional, TypedDict

from ..trust import normalize_author_association

if TYPE_CHECKING:
    from github.Issue import Issue


class IssueEventType(str, Enum):
    """Enum for GitHub issue event types."""

    # Label events
    LABELED = "labeled"
    UNLABELED = "unlabeled"

    # State events
    CLOSED = "closed"
    REOPENED = "reopened"

    # Assignment events
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"

    # Milestone events
    MILESTONED = "milestoned"
    DEMILESTONED = "demilestoned"

    # Reference events
    REFERENCED = "referenced"
    CROSS_REFERENCED = "cross-referenced"

    # Interaction events
    COMMENTED = "commented"
    MENTIONED = "mentioned"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"

    # Title/Lock events
    RENAMED = "renamed"
    LOCKED = "locked"
    UNLOCKED = "unlocked"

    # PR-specific events (included for completeness)
    REVIEW_REQUESTED = "review_requested"
    REVIEW_REQUEST_REMOVED = "review_request_removed"
    CONVERTED_TO_DRAFT = "converted_to_draft"
    READY_FOR_REVIEW = "ready_for_review"


class IssueData(TypedDict):
    """TypedDict for issue data structure.

    Represents a GitHub issue with all relevant fields returned from the GitHub API.
    """

    number: int
    title: str
    body: str
    state: str
    labels: List[str]
    assignees: List[str]
    user: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    url: str
    locked: bool
    author_association: Optional[str]
    base_branch: NotRequired[Optional[str]]
    base_branch_error: NotRequired[Optional[str]]


class CommentData(TypedDict):
    """TypedDict for issue comment data structure.

    Represents a comment on a GitHub issue with all relevant fields.
    """

    id: int
    body: str
    user: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    url: str
    author_association: Optional[str]


class EventData(TypedDict):
    """TypedDict for issue event data structure."""

    event: str  # Event type (e.g., "labeled", "unlabeled")
    label: Optional[str]  # Label name (for label events)
    created_at: str  # ISO format timestamp
    actor: Optional[str]  # GitHub username who performed action


def create_empty_issue_data() -> IssueData:
    """Create an empty IssueData structure for error cases.

    Returns:
        IssueData with default/empty values for all fields.
    """
    return IssueData(
        number=0,
        title="",
        body="",
        state="",
        labels=[],
        assignees=[],
        user=None,
        created_at=None,
        updated_at=None,
        url="",
        locked=False,
        author_association=None,
    )


def issue_to_data(github_issue: "Issue") -> IssueData:
    """Convert a PyGithub Issue into IssueData.

    Does not populate ``base_branch`` / ``base_branch_error`` — callers that
    need them parse the body themselves.

    Args:
        github_issue: PyGithub Issue to convert

    Returns:
        IssueData with the issue's current fields
    """
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
        author_association=normalize_author_association(
            github_issue.author_association
        ),
    )


__all__ = [
    "IssueEventType",
    "IssueData",
    "CommentData",
    "EventData",
    "create_empty_issue_data",
    "issue_to_data",
]
