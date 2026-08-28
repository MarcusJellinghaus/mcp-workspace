"""Formatters for GitHub issue and PR data.

Pure formatting functions that take data dicts and return formatted text strings.
No API calls or manager dependencies.
"""

from typing import Any, Optional, TypedDict

from mcp_workspace.github_operations.issues.types import CommentData, IssueData


class ReviewData(TypedDict):
    """Data for a PR review."""

    user: Optional[str]
    state: str  # APPROVED, CHANGES_REQUESTED, COMMENTED
    body: str


class InlineCommentData(TypedDict):
    """Data for an inline review comment."""

    path: str
    line: Optional[int]
    user: Optional[str]
    body: str


def truncate_output(text: str, max_lines: int) -> str:
    """Apply max_lines truncation with indicator.

    Args:
        text: The text to potentially truncate.
        max_lines: Maximum number of lines to keep. Negative values are
            treated as 0.

    Returns:
        Original text if within limit, otherwise truncated with indicator.
    """
    # max_lines arrives straight from the unvalidated github_issue_view /
    # github_pr_view parameter, so clamp it before anything derives from it:
    # a negative cap made lines[:max_lines] keep all but the last line under a
    # notice reading "showing -1 of {total}".
    max_lines = max(0, max_lines)
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    total = len(lines)
    return "\n".join(lines[:max_lines]) + (
        f"\n\n... truncated: showing {max_lines} of {total} lines. "
        f"Pass max_lines={total} for the full output."
    )


def format_issue_view(
    issue: IssueData,
    comments: list[CommentData],
    max_lines: int = 200,
) -> str:
    """Format a single issue with full detail for LLM consumption.

    Args:
        issue: Issue data dict.
        comments: List of comment data dicts.
        max_lines: Maximum output lines before truncation.

    Returns:
        Formatted multi-line text string.
    """
    parts: list[str] = [f"# #{issue['number']}: {issue['title']}"]

    labels = ", ".join(issue["labels"]) if issue["labels"] else "none"
    assignees = ", ".join(issue["assignees"]) if issue["assignees"] else "none"
    parts.append(f"State: {issue['state']} | Labels: {labels} | Assignees: {assignees}")

    parts.append(issue["body"] or "(no description)")

    if comments:
        parts.append(f"## Comments ({len(comments)})")
        for comment in comments:
            parts.append(
                f"**{comment['user']}** ({comment['created_at']}):\n{comment['body']}"
            )

    return truncate_output("\n\n".join(parts), max_lines)


def format_issue_list(
    issues: list[IssueData],
    max_results: int = 30,
) -> str:
    """Format issue list as compact summary lines.

    The truncation notice is driven by the caller's over-fetch. Issue listing
    has no total count, so the only evidence that more results exist is a
    surplus item: callers must fetch with a limit of `max_results + 1` and pass
    `max_results` unchanged. This function then displays the first
    `max_results` issues and renders the "30+" notice when the surplus item is
    present.

    Passing a list already capped at `max_results` makes the notice condition
    unreachable, so the list truncates silently. That is the bug this contract
    exists to prevent.

    Args:
        issues: Issue data dicts, fetched with a limit of `max_results + 1` so
            the surplus item can prove that more results exist. At most
            `max_results` of them are displayed.
        max_results: Maximum number of issues to display. Must be the
            unincremented cap, not the limit used to fetch `issues`. Negative
            values are treated as 0.

    Returns:
        Compact one-line-per-issue text, with a truncation notice when the
        surplus item is present. A cap of 0 renders the notice alone; only a
        genuinely empty `issues` renders "No issues found."
    """
    max_results = max(0, max_results)
    displayed = issues[:max_results]
    # Emptiness is judged on the over-fetched list, not the capped one:
    # "No issues found." must mean the listing was empty, never that the cap
    # was 0 while the over-fetch proved issues exist.
    if not issues:
        return "No issues found."
    if not displayed:
        # A cap of 0 displays nothing, so the notice is the whole render —
        # returned bare rather than under a blank line and an empty list.
        return "... showing 0 of 0+ results — raise max_results to see them."

    lines: list[str] = []
    for issue in displayed:
        labels_str = ", ".join(issue["labels"]) if issue["labels"] else ""
        label_part = f"  {labels_str}" if labels_str else ""
        lines.append(
            f"#{issue['number']} [{issue['state']}] {issue['title']}{label_part}"
        )

    if len(issues) > max_results:
        lines.append(
            f"\n... showing {max_results} of {max_results}+ results "
            f"— raise max_results or narrow with state/labels/assignee/since."
        )

    return "\n".join(lines)


def format_pr_view(
    pr: dict[str, Any],
    reviews: Optional[list[ReviewData]] = None,
    conversation_comments: Optional[list[CommentData]] = None,
    inline_comments: Optional[list[InlineCommentData]] = None,
    max_lines: int = 200,
) -> str:
    """Format a single PR with full detail for LLM consumption.

    Args:
        pr: PR data dict with number, title, state, head_branch, base_branch, etc.
        reviews: Optional list of review data dicts.
        conversation_comments: Optional list of conversation comment dicts.
        inline_comments: Optional list of inline review comment dicts.
        max_lines: Maximum output lines before truncation.

    Returns:
        Formatted multi-line text string.
    """
    parts: list[str] = [f"# PR #{pr['number']}: {pr['title']}"]

    draft = pr.get("draft", False)
    merged = pr.get("merged", False)
    parts.append(
        f"State: {pr['state']} | {pr['head_branch']} → {pr['base_branch']}"
        f" | Draft: {draft} | Merged: {merged}"
    )

    parts.append(pr.get("body") or "(no description)")

    if reviews:
        parts.append("## Reviews")
        for review in reviews:
            parts.append(f"**{review['user']}**: {review['state']}\n{review['body']}")

    if conversation_comments:
        parts.append(f"## Comments ({len(conversation_comments)})")
        for comment in conversation_comments:
            parts.append(
                f"**{comment['user']}** ({comment['created_at']}):\n{comment['body']}"
            )

    if inline_comments:
        parts.append(f"## Inline Review Comments ({len(inline_comments)})")
        for ic in inline_comments:
            line_num = ic["line"] if ic["line"] is not None else "?"
            parts.append(f"{ic['path']}:{line_num} ({ic['user']}): \"{ic['body']}\"")

    return truncate_output("\n\n".join(parts), max_lines)


def format_search_results(
    items: list[dict[str, Any]],
    max_results: int = 30,
    total_count: Optional[int] = None,
) -> str:
    """Format search results as compact summary lines.

    Args:
        items: List of search result dicts with number, title, state, labels, etc.
        max_results: Maximum number of results to display.
        total_count: Exact total from the search API when known; falls back to
            len(items).

    Returns:
        Compact one-line-per-result text with Issue/PR indicator.
    """
    if not items:
        return "No results found."

    lines: list[str] = []
    for item in items[:max_results]:
        kind = "PR" if item.get("pull_request") else "Issue"
        labels = ", ".join(item.get("labels", []))
        label_part = f"  {labels}" if labels else ""
        lines.append(
            f"#{item['number']} [{kind}] [{item['state']}] {item['title']}{label_part}"
        )

    # lines was built from items[:max_results], so its length is exactly the
    # number of results actually shown.
    shown = len(lines)
    total = total_count if total_count is not None else len(items)
    if total > shown:
        lines.append(
            f"\n... showing {shown} of {total} results "
            f"— raise max_results or refine your query."
        )

    return "\n".join(lines)
