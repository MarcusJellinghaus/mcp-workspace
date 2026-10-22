"""Tests for GitHub issue formatters."""

import pytest

from mcp_workspace.github_operations.formatters import (
    find_latest_marked_comment,
    format_issue_list,
    format_issue_view,
    format_search_results,
    format_withheld_line,
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
    author_association: str | None = "OWNER",
) -> CommentData:
    """Create a test CommentData dict."""
    return CommentData(
        id=1,
        body=body,
        user=user,
        created_at=created_at,
        updated_at=None,
        url="https://github.com/owner/repo/issues/42#comment-1",
        author_association=author_association,
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

    def test_truncate_output_negative_max_lines(self) -> None:
        """A negative cap keeps nothing and never reports a negative count."""
        text = "\n".join(f"line{i}" for i in range(10))
        result = truncate_output(text, max_lines=-1)
        assert "line0" not in result
        assert "line9" not in result
        assert "showing 0 of 10 lines" in result
        assert "max_lines=10" in result
        assert "-1" not in result

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

    @pytest.mark.parametrize(
        ("linked_branches", "expected_line"),
        [
            (["1176-adopt-deptry"], "Linked branches: 1176-adopt-deptry"),
            (["12-a", "12-b"], "Linked branches: 12-a, 12-b"),
            ([], "Linked branches: none"),
            (None, "Linked branches: unknown (lookup failed)"),
        ],
    )
    def test_format_issue_view_linked_branches(
        self, linked_branches: list[str] | None, expected_line: str
    ) -> None:
        """Linked-branches line rendered as line 4, under the State line."""
        result = format_issue_view(
            _make_issue(),
            comments=[],
            linked_branches=linked_branches,
            include_linked_branches=True,
        )
        assert result.splitlines()[3] == expected_line

    def test_format_issue_view_linked_branches_not_requested(self) -> None:
        """No linked-branches line when the flag is off."""
        issue = _make_issue()
        assert "Linked branches" not in format_issue_view(issue, comments=[])
        result = format_issue_view(issue, comments=[], linked_branches=["x"])
        assert "Linked branches" not in result

    def test_format_issue_view_linked_branches_survives_max_lines_4(self) -> None:
        """Linked-branches line kept when output is truncated to 4 lines."""
        issue = _make_issue(body="\n".join(f"line {i}" for i in range(300)))
        result = format_issue_view(
            issue,
            comments=[],
            max_lines=4,
            linked_branches=["42-x"],
            include_linked_branches=True,
        )
        assert "Linked branches: 42-x" in result


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

    def test_format_issue_list_empty_names_repo(self) -> None:
        """Empty result names the repository when it is known."""
        result = format_issue_list([], repo_full_name="owner/repo")
        assert result == "No issues found in owner/repo."

    def test_format_issue_list_max_results_cap(self) -> None:
        """Excess issues truncated with guidance."""
        issues = [_make_issue(number=i, title=f"Issue {i}") for i in range(5)]
        result = format_issue_list(issues, max_results=3)
        assert "#0" in result
        assert "#1" in result
        assert "#2" in result
        assert "#3" not in result
        # The lower bound is the length of the list handed in, not the cap.
        assert "showing 3 of 5+ results" in result
        assert "raise max_results" in result
        assert "state/labels/assignee/since" in result
        assert "query" not in result  # this tool has no query parameter

    @pytest.mark.parametrize("max_results", [0, -1])
    def test_format_issue_list_non_positive_max_results(self, max_results: int) -> None:
        """A non-positive cap renders the notice alone, with no negative count."""
        issues = [_make_issue(number=i, title=f"Issue {i}") for i in range(3)]
        result = format_issue_list(issues, max_results=max_results)
        # One spelling of the notice, and a lower bound the caller proved.
        assert result == (
            "... showing 0 of 3+ results "
            "— raise max_results or narrow with state/labels/assignee/since."
        )

    def test_format_issue_list_empty_distinguished_from_zero_cap(self) -> None:
        """The empty message means empty, never that the cap was 0."""
        issues = [_make_issue(number=i, title=f"Issue {i}") for i in range(3)]

        assert format_issue_list([], max_results=0) == "No issues found."

        capped = format_issue_list(issues, max_results=0)
        assert "No issues found." not in capped
        assert "raise max_results" in capped

    def test_format_issue_list_labels(self) -> None:
        """Labels rendered in summary line."""
        issues = [_make_issue(number=1, title="Labeled", labels=["bug", "help wanted"])]
        result = format_issue_list(issues)
        assert "bug" in result
        assert "help wanted" in result


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

    @pytest.mark.parametrize("max_results", [0, -1])
    def test_format_search_results_non_positive_max_results(
        self, max_results: int
    ) -> None:
        """A non-positive cap reports suppression, not an empty result set.

        Such a call collects nothing whatever the search matched, so it never
        established that there were no results, and has no total to report.
        """
        result = format_search_results([], max_results=max_results)
        assert result == (
            "... showing 0 of an unknown total — a max_results cap of 0 "
            "suppressed the output; raise max_results to see results."
        )

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


# --- format_withheld_line tests ---


class TestFormatWithheldLine:
    """Tests for format_withheld_line."""

    def test_all_zeros_returns_none(self) -> None:
        assert format_withheld_line([("thread", 0), ("review", 0)]) is None

    def test_empty_returns_none(self) -> None:
        assert format_withheld_line([]) is None

    def test_pluralises_and_skips_zero_counts(self) -> None:
        result = format_withheld_line([("thread", 2), ("review", 1), ("comment", 0)])
        assert result == (
            "Withheld from untrusted authors: 2 threads, 1 review — review on GitHub"
        )


# --- find_latest_marked_comment tests ---


class TestFindLatestMarkedComment:
    """Tests for find_latest_marked_comment."""

    def test_find_latest_marked_comment_empty_list(self) -> None:
        """An empty comments list returns None."""
        assert find_latest_marked_comment([]) is None

    def test_find_latest_marked_comment_single_match(self) -> None:
        """A single comment with the marker on its first line is returned."""
        body = "❌ Failed\nSome details\nmore details"
        comments = [_make_comment(body=body)]
        assert find_latest_marked_comment(comments) is comments[0]

    def test_find_latest_marked_comment_marker_in_heading(self) -> None:
        """The marker matches as a substring, not a prefix, inside a heading."""
        body = "## ❌ Implementation Failed\nDetails here"
        comments = [_make_comment(body=body)]
        assert find_latest_marked_comment(comments) is comments[0]

    def test_find_latest_marked_comment_skips_empty_body(self) -> None:
        """A comment with an empty body is skipped without raising."""
        comments = [_make_comment(body="")]
        assert find_latest_marked_comment(comments) is None

    def test_find_latest_marked_comment_outside_window_not_found(self) -> None:
        """A match older than the window is not found."""
        comments = [
            _make_comment(body="❌ Old failure"),
            _make_comment(body="unrelated 1"),
            _make_comment(body="unrelated 2"),
            _make_comment(body="unrelated 3"),
        ]
        assert find_latest_marked_comment(comments, window=3) is None

    def test_find_latest_marked_comment_most_recent_wins(self) -> None:
        """When two comments in the window match, the more recent one wins."""
        comments = [
            _make_comment(body="❌ Older failure"),
            _make_comment(body="❌ Newer failure"),
        ]
        assert find_latest_marked_comment(comments) is comments[1]

    def test_find_latest_marked_comment_no_match(self) -> None:
        """No comment in the window matches returns None."""
        comments = [
            _make_comment(body="all good"),
            _make_comment(body="still fine"),
        ]
        assert find_latest_marked_comment(comments) is None

    def test_find_latest_marked_comment_custom_marker_and_window(self) -> None:
        """Custom marker and window arguments are respected."""
        comments = [
            _make_comment(body="no marker here"),
            _make_comment(body="no marker here either"),
            _make_comment(body="⚠️ warning in window"),
        ]
        assert (
            find_latest_marked_comment(comments, marker="⚠️", window=1) is comments[2]
        )
        assert find_latest_marked_comment(comments[:-1], marker="⚠️", window=2) is None
