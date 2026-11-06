"""Type definitions for pull request operations.

This module contains TypedDict definitions used across the PullRequestManager
and its mixins.
"""

from typing import Literal, TypedDict


class PullRequestData(TypedDict):
    """TypedDict for pull request data structure."""

    number: int
    title: str
    body: str
    state: str
    head_branch: str
    head_sha: str | None
    base_branch: str
    url: str
    created_at: str | None
    updated_at: str | None
    user: str | None
    mergeable: bool | None
    mergeable_state: str | None
    merged: bool
    draft: bool
    assignees: list[str]
    author_association: str | None


class ReviewThreadData(TypedDict):
    """TypedDict for one unresolved review thread, described by its first comment."""

    path: str
    line: int | None
    author: str
    body: str
    diff_hunk: str
    comment_id: int | None
    thread_id: str | None
    author_association: str | None


class AlertData(TypedDict):
    """TypedDict for one open code-scanning alert on a PR."""

    number: int
    rule_id: str
    rule_description: str
    message: str
    path: str
    line: int | None


class AlertsResult(TypedDict):
    """Code-scanning alerts of a PR head, as returned by ``PullRequestCache.alerts()``."""

    alerts: list[AlertData]
    skipped: int | None  # HTTP status (403/404) when alerts could not be checked
    final: bool  # every CI run on head_sha completed; always True on a stored hit


class ConversationCommentData(TypedDict):
    """TypedDict for a PR top-level conversation comment."""

    author: str
    body: str
    id: int
    created_at: str | None
    author_association: str | None


class ChangesRequestedData(TypedDict):
    """TypedDict for one standing CHANGES_REQUESTED review."""

    author: str
    body: str
    submitted_at: str | None
    author_association: str | None


class PRFeedback(TypedDict):
    """TypedDict for aggregated PR feedback (review threads, standing CHANGES_REQUESTED reviews, comments, alerts)."""

    unresolved_threads: list[ReviewThreadData]
    resolved_thread_count: int
    changes_requested: list[ChangesRequestedData]
    conversation_comments: list[ConversationCommentData]
    alerts: list[AlertData]
    unavailable: dict[str, Exception]
    skipped: dict[str, Exception]


class MergeResult(TypedDict):
    """Outcome of a merge attempt."""

    merged: bool
    outcome: Literal["merged", "refused", "error"]
    sha: str | None  # merge commit SHA when merged
    message: str  # GitHub's message, or the local failure reason
    status: int | None  # HTTP status when GitHub answered (405, 409, 5xx...)
