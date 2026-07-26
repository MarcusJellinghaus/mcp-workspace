"""PR feedback formatting and collection helpers.

Extracted from `branch_status.py` to keep that module under the file-size
threshold. The functions here render `PRFeedback` dicts as text and wrap
`PullRequestManager.get_pr_feedback()` with logging-friendly error handling.
"""

import logging
from typing import List, Optional, Tuple

from mcp_workspace.github_operations.exception_renderer import (
    render_exception_for_display,
)
from mcp_workspace.github_operations.pr_manager import PRFeedback, PullRequestManager

logger = logging.getLogger(__name__)

_MAX_FEEDBACK_ITEMS = 20
_MAX_LINES_PER_COMMENT = 10


def _truncate_body(body: str) -> str:
    """Truncate a comment body at `_MAX_LINES_PER_COMMENT` lines.

    Returns:
        The body, truncated with a "... (truncated)" marker if too long.
    """
    lines = body.splitlines()
    if len(lines) <= _MAX_LINES_PER_COMMENT:
        return body
    return "\n".join(lines[:_MAX_LINES_PER_COMMENT]) + "\n... (truncated)"


def format_pr_feedback(feedback: PRFeedback) -> str:
    """Render a `PRFeedback` dict as a multi-line block.

    Returns:
        The empty-state affirmation when there is nothing to surface,
        otherwise a `PR Reviews:` block. No trailing newline.
    """
    unresolved = feedback["unresolved_threads"]
    comments = feedback["conversation_comments"]
    changes_requested = feedback["changes_requested"]
    alerts = feedback["alerts"]
    unavailable = feedback["unavailable"]
    resolved_count = feedback["resolved_thread_count"]

    blocking = bool(unresolved or changes_requested or alerts)
    if not blocking and not comments and not unavailable:
        return "Reviews: clean (0 unresolved threads, 0 alerts)"

    rendered: List[str] = []

    for thread in unresolved:
        path = thread.get("path", "")
        line_no = thread.get("line")
        author = thread.get("author", "")
        diff_hunk = thread.get("diff_hunk", "")
        body = _truncate_body(thread.get("body", ""))
        indented_hunk = "\n".join(f"  {line}" for line in diff_hunk.splitlines())
        location = f"{path}:{line_no}" if line_no else path
        rendered.append(
            f"[unresolved thread] {location} ({author}):\n"
            f"{indented_hunk}\n"
            f"  Comment: {body}"
        )

    for comment in comments:
        author = comment.get("author", "")
        body = _truncate_body(comment.get("body", ""))
        rendered.append(f"[comment] {author}:\n  {body}")

    for review in changes_requested:
        author = review.get("author", "")
        body = _truncate_body(review.get("body", ""))
        rendered.append(f"[changes_requested] {author}: {body}")

    for alert in alerts:
        rule = alert.get("rule_description", "")
        message = alert.get("message", "")
        path = alert.get("path", "")
        line_no = alert.get("line")
        location = f"{path}:{line_no}" if line_no else path
        rendered.append(f"[alert] {rule}: {message} @ {location}")

    total = len(rendered)
    if total > _MAX_FEEDBACK_ITEMS:
        kept = rendered[:_MAX_FEEDBACK_ITEMS]
        kept.append(f"... and {total - _MAX_FEEDBACK_ITEMS} more")
        rendered = kept

    lines: List[str] = ["PR Reviews:"]
    lines.extend(rendered)

    for section, exc in unavailable.items():
        lines.append(f"[unavailable] {section}: {render_exception_for_display(exc)}")

    if resolved_count > 0:
        lines.append(f"{resolved_count} resolved threads")

    return "\n".join(lines)


def collect_pr_feedback(
    pr_manager: PullRequestManager, pr_number: int
) -> Tuple[Optional[str], bool]:
    """Fetch PR feedback for a pull request.

    Returns:
        Tuple of (formatted_text, blocks_merge), or (None, False) on
        total failure (logged at debug level).
    """
    try:
        feedback = pr_manager.get_pr_feedback(pr_number)
        text = format_pr_feedback(feedback)
        blocks_merge = bool(
            feedback["unresolved_threads"]
            or feedback["changes_requested"]
            or feedback["alerts"]
        )
        return (text, blocks_merge)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("PR feedback collection failed", exc_info=True)
        return (None, False)
