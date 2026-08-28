"""Tests for GitHub issue formatters."""

from typing import Any, Dict

from mcp_workspace.github_operations.formatters import (
    InlineCommentData,
    ReviewData,
    format_issue_list,
    format_issue_view,
    format_pr_view,
    format_search_results,
    truncate_output,
)
from mcp_workspace.github_operations.issues.types import CommentData, IssueData


def _make_issue(
    number: int = 42,
    title: str = "Test issue",
    body: str = "Issue body text",
    state: str = "open",
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> IssueData:
    """Create a test IssueData dict."""
    return IssueData(
        number=number,
        title=title,
        body=body,
        state=state,
        labels=labels or [],
        assignees=assignees or [],
        user="testuser",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-02T00:00:00Z",
        url=f"https://github.com/owner/repo/issues/{number}",
        locked=False,
    )


def _make_comment(
    body: str = "Comment text",
    user: str = "commenter",
    created_at: str = "2024-01-03T00:00:00Z",
) -> CommentData:
    """Create a test CommentData dict."""
    return CommentData(
        id=1,
        body=body,
        user=user,
        created_at=created_at,
        updated_at=None,
        url="https://github.com/owner/repo/issues/42#comment-1",
    )


# --- truncate_output tests ---


class TestTruncateOutput:
    """Tests for truncate_output."""

    def test_truncate_output_no_truncation(self) -> None:
        """Text within limit returned as-is."""
        text = "line1\nline2\nline3"
        result = truncate_output(text, max_lines=5)
        assert result == text

    def test_truncate_output_truncation(self) -> None:
        """Text exceeding limit truncated with indicator."""
        text = "\n".join(f"line{i}" for i in range(10))
        result = truncate_output(text, max_lines=3)
        assert "line0" in result
        assert "line1" in result
        assert "line2" in result
        assert "line3" not in result
        assert "showing 3 of 10 lines" in result
        assert "max_lines=10" in result

    def test_truncate_output_exact_limit(self) -> None:
        """Text at exact limit not truncated."""
        text = "\n".join(f"line{i}" for i in range(5))
        result = truncate_output(text, max_lines=5)
        assert result == text
        assert "truncated" not in result


# --- format_issue_view tests ---


class TestFormatIssueView:
    """Tests for format_issue_view."""

    def test_format_issue_view_basic(self) -> None:
        """Title, state, labels, body rendered."""
        issue = _make_issue(
            number=42,
            title="Bug report",
            body="Something broke",
            state="open",
            labels=["bug", "urgent"],
            assignees=["alice"],
        )
        result = format_issue_view(issue, comments=[])
        assert "# #42: Bug report" in result
        assert "open" in result
        assert "bug" in result
        assert "urgent" in result
        assert "alice" in result
        assert "Something broke" in result

    def test_format_issue_view_with_comments(self) -> None:
        """Comments section rendered."""
        issue = _make_issue()
        comments = [
            _make_comment(
                body="First comment",
                user="alice",
                created_at="2024-01-03T00:00:00Z",
            ),
            _make_comment(
                body="Second comment",
                user="bob",
                created_at="2024-01-04T00:00:00Z",
            ),
        ]
        result = format_issue_view(issue, comments=comments)
        assert "Comments (2)" in result
        assert "**alice**" in result
        assert "First comment" in result
        assert "**bob**" in result
        assert "Second comment" in result

    def test_format_issue_view_no_comments(self) -> None:
        """No comments section when empty list."""
        issue = _make_issue()
        result = format_issue_view(issue, comments=[])
        assert "Comments" not in result

    def test_format_issue_view_truncation(self) -> None:
        """Long output truncated with indicator."""
        issue = _make_issue(body="\n".join(f"line {i}" for i in range(300)))
        result = format_issue_view(issue, comments=[], max_lines=10)
        assert "showing 10 of 304 lines" in result
        assert "max_lines=304" in result

    def test_format_issue_view_empty_body(self) -> None:
        """'(no description)' placeholder for empty body."""
        issue = _make_issue(body="")
        result = format_issue_view(issue, comments=[])
        assert "(no description)" in result


# --- format_issue_list tests ---


class TestFormatIssueList:
    """Tests for format_issue_list."""

    def test_format_issue_list_basic(self) -> None:
        """Renders summary lines."""
        issues = [
            _make_issue(number=1, title="First issue", state="open"),
            _make_issue(number=2, title="Second issue", state="closed"),
        ]
        result = format_issue_list(issues)
        assert "#1 [open] First issue" in result
        assert "#2 [closed] Second issue" in result

    def test_format_issue_list_empty(self) -> None:
        """'No issues found.' message."""
        result = format_issue_list([])
        assert result == "No issues found."

    def test_format_issue_list_max_results_cap(self) -> None:
        """Excess issues truncated with guidance."""
        issues = [_make_issue(number=i, title=f"Issue {i}") for i in range(5)]
        result = format_issue_list(issues, max_results=3)
        assert "#0" in result
        assert "#1" in result
        assert "#2" in result
        assert "#3" not in result
        assert "showing 3 of 3+ results" in result
        assert "raise max_results" in result
        assert "state/labels/assignee/since" in result
        assert "query" not in result  # this tool has no query parameter

    def test_format_issue_list_labels(self) -> None:
        """Labels rendered in summary line."""
        issues = [_make_issue(number=1, title="Labeled", labels=["bug", "help wanted"])]
        result = format_issue_list(issues)
        assert "bug" in result
        assert "help wanted" in result


# --- Helper for PR tests ---


def _make_pr(
    number: int = 99,
    title: str = "Test PR",
    body: str = "PR body text",
    state: str = "open",
    head_branch: str = "feature-branch",
    base_branch: str = "main",
    draft: bool = False,
    merged: bool = False,
) -> Dict[str, Any]:
    """Create a test PR data dict."""
    return {
        "number": number,
        "title": title,
        "body": body,
        "state": state,
        "head_branch": head_branch,
        "base_branch": base_branch,
        "draft": draft,
        "merged": merged,
    }


# --- format_pr_view tests ---


class TestFormatPrView:
    """Tests for format_pr_view."""

    def test_format_pr_view_basic(self) -> None:
        """Title, state, branches, body rendered."""
        pr = _make_pr(
            number=99,
            title="Add feature",
            body="This adds a feature",
            state="open",
            head_branch="feat/thing",
            base_branch="main",
        )
        result = format_pr_view(pr)
        assert "# PR #99: Add feature" in result
        assert "open" in result
        assert "feat/thing" in result
        assert "main" in result
        assert "This adds a feature" in result

    def test_format_pr_view_with_reviews(self) -> None:
        """Review verdicts rendered."""
        pr = _make_pr()
        reviews: list[ReviewData] = [
            ReviewData(user="alice", state="APPROVED", body="LGTM"),
            ReviewData(user="bob", state="CHANGES_REQUESTED", body="Fix the tests"),
        ]
        result = format_pr_view(pr, reviews=reviews)
        assert "## Reviews" in result
        assert "**alice**: APPROVED" in result
        assert "LGTM" in result
        assert "**bob**: CHANGES_REQUESTED" in result
        assert "Fix the tests" in result

    def test_format_pr_view_with_conversation_comments(self) -> None:
        """Conversation comments rendered."""
        pr = _make_pr()
        comments = [
            _make_comment(
                body="Looks good",
                user="alice",
                created_at="2024-01-05T00:00:00Z",
            ),
            _make_comment(body="Thanks", user="bob", created_at="2024-01-06T00:00:00Z"),
        ]
        result = format_pr_view(pr, conversation_comments=comments)
        assert "## Comments (2)" in result
        assert "**alice**" in result
        assert "Looks good" in result
        assert "**bob**" in result
        assert "Thanks" in result

    def test_format_pr_view_with_inline_comments(self) -> None:
        """Compact path:line (user): 'body' format."""
        pr = _make_pr()
        inline: list[InlineCommentData] = [
            InlineCommentData(
                path="src/main.py",
                line=42,
                user="alice",
                body="Nit: rename this",
            ),
        ]
        result = format_pr_view(pr, inline_comments=inline)
        assert "## Inline Review Comments (1)" in result
        assert 'src/main.py:42 (alice): "Nit: rename this"' in result

    def test_format_pr_view_no_comments(self) -> None:
        """No comment sections when all None."""
        pr = _make_pr()
        result = format_pr_view(pr)
        assert "Reviews" not in result
        assert "Comments" not in result
        assert "Inline" not in result

    def test_format_pr_view_truncation(self) -> None:
        """Long output truncated with indicator."""
        pr = _make_pr(body="\n".join(f"line {i}" for i in range(300)))
        result = format_pr_view(pr, max_lines=10)
        assert "truncated" in result

    def test_format_pr_view_merged_draft_flags(self) -> None:
        """Merged/draft status displayed."""
        pr = _make_pr(draft=True, merged=False)
        result = format_pr_view(pr)
        assert "Draft: True" in result
        assert "Merged: False" in result

        pr_merged = _make_pr(draft=False, merged=True)
        result_merged = format_pr_view(pr_merged)
        assert "Draft: False" in result_merged
        assert "Merged: True" in result_merged


# --- format_search_results tests ---


class TestFormatSearchResults:
    """Tests for format_search_results."""

    def test_format_search_results_basic(self) -> None:
        """Renders summary lines."""
        items = [
            {"number": 1, "title": "Bug fix", "state": "open", "labels": ["bug"]},
            {"number": 2, "title": "Feature", "state": "closed", "labels": []},
        ]
        result = format_search_results(items)
        assert "#1 [Issue] [open] Bug fix  bug" in result
        assert "#2 [Issue] [closed] Feature" in result

    def test_format_search_results_empty(self) -> None:
        """'No results found.' message."""
        result = format_search_results([])
        assert result == "No results found."

    def test_format_search_results_issue_vs_pr(self) -> None:
        """Correct Issue/PR indicator."""
        items = [
            {"number": 1, "title": "An issue", "state": "open", "labels": []},
            {
                "number": 2,
                "title": "A PR",
                "state": "open",
                "labels": [],
                "pull_request": {"url": "https://..."},
            },
        ]
        result = format_search_results(items)
        assert "#1 [Issue]" in result
        assert "#2 [PR]" in result

    def test_format_search_results_max_results_cap(self) -> None:
        """Excess results truncated with guidance."""
        items = [
            {"number": i, "title": f"Result {i}", "state": "open", "labels": []}
            for i in range(5)
        ]
        result = format_search_results(items, max_results=3)
        assert "#0" in result
        assert "#1" in result
        assert "#2" in result
        assert "#3" not in result
        assert "showing 3 of 5 results" in result
        assert "raise max_results" in result
        assert "refine your query" in result

    def test_format_search_results_uses_total_count(self) -> None:
        """An explicit total_count is rendered instead of len(items)."""
        items = [
            {"number": i, "title": f"Result {i}", "state": "open", "labels": []}
            for i in range(3)
        ]
        result = format_search_results(items, max_results=3, total_count=412)
        assert "showing 3 of 412 results" in result
