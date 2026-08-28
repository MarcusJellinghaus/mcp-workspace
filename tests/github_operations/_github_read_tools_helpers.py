"""Shared helpers for the GitHub read-only MCP tool tests."""

from unittest.mock import MagicMock

from mcp_workspace.github_operations.issues.types import CommentData, IssueData


def make_issue(
    number: int = 42,
    title: str = "Test issue",
    body: str = "Issue body text",
    state: str = "open",
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> IssueData:
    """Create an IssueData for testing."""
    return IssueData(
        number=number,
        title=title,
        body=body,
        state=state,
        labels=labels or ["bug"],
        assignees=assignees or ["alice"],
        user="alice",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-02T00:00:00",
        url="https://github.com/test/repo/issues/42",
        locked=False,
    )


def make_comment(
    comment_id: int = 1,
    body: str = "A comment",
    user: str = "bob",
) -> CommentData:
    """Create a CommentData for testing."""
    return CommentData(
        id=comment_id,
        body=body,
        user=user,
        created_at="2024-01-03T00:00:00",
        updated_at=None,
        url="https://github.com/test/repo/issues/42#issuecomment-1",
    )


def mock_pull(
    number: int = 10,
    title: str = "Fix bug",
    body: str = "PR body text",
    state: str = "open",
    draft: bool = False,
    merged: bool = False,
    head_branch: str = "feature",
    base_branch: str = "main",
) -> MagicMock:
    """Create a mock PR object resembling PyGithub PullRequest."""
    pr = MagicMock()
    pr.number = number
    pr.title = title
    pr.body = body
    pr.state = state
    pr.draft = draft
    pr.merged = merged
    pr.head.ref = head_branch
    pr.base.ref = base_branch
    pr.get_reviews.return_value = []
    pr.get_review_comments.return_value = []
    return pr
