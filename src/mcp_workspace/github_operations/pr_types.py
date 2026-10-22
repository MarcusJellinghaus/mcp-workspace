"""Type definitions for pull request operations.

This module contains TypedDict definitions used across the PullRequestManager
and its mixins.
"""

from typing import Any, Literal, Optional, TypedDict


class PullRequestData(TypedDict):
    """TypedDict for pull request data structure."""

    number: int
    title: str
    body: str
    state: str
    head_branch: str
    head_sha: Optional[str]
    base_branch: str
    url: str
    created_at: Optional[str]
    updated_at: Optional[str]
    user: Optional[str]
    mergeable: Optional[bool]
    mergeable_state: Optional[str]
    merged: bool
    draft: bool
    assignees: list[str]
    author_association: Optional[str]


class ReviewThreadData(TypedDict):
    """TypedDict for one unresolved review thread, described by its first comment."""

    path: str
    line: Optional[int]
    author: str
    body: str
    diff_hunk: str
    comment_id: Optional[int]
    thread_id: Optional[str]
    author_association: Optional[str]


class ConversationCommentData(TypedDict):
    """TypedDict for a PR top-level conversation comment."""

    author: str
    body: str
    id: int
    created_at: Optional[str]
    author_association: Optional[str]


class ChangesRequestedData(TypedDict):
    """TypedDict for one standing CHANGES_REQUESTED review."""

    author: str
    body: str
    submitted_at: Optional[str]
    author_association: Optional[str]


class PRFeedback(TypedDict):
    """TypedDict for aggregated PR feedback (review threads, standing CHANGES_REQUESTED reviews, comments, alerts)."""

    unresolved_threads: list[ReviewThreadData]
    resolved_thread_count: int
    changes_requested: list[ChangesRequestedData]
    conversation_comments: list[ConversationCommentData]
    alerts: list[dict[str, Any]]
    unavailable: dict[str, Exception]


class MergeResult(TypedDict):
    """Outcome of a merge attempt."""

    merged: bool
    outcome: Literal["merged", "refused", "error"]
    sha: Optional[str]  # merge commit SHA when merged
    message: str  # GitHub's message, or the local failure reason
    status: Optional[int]  # HTTP status when GitHub answered (405, 409, 5xx...)
