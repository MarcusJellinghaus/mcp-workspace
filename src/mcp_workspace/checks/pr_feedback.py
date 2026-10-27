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
from mcp_workspace.github_operations.formatters import format_withheld_line
from mcp_workspace.github_operations.pr_manager import PullRequestManager
from mcp_workspace.github_operations.pr_types import (
    ChangesRequestedData,
    ConversationCommentData,
    PRFeedback,
    ReviewThreadData,
)
from mcp_workspace.github_operations.trust import is_trusted_author

logger = logging.getLogger(__name__)

# Deliberate internal caps with no lift parameter: this block is a compact
# summary embedded in the branch-status report, not a full feedback dump.
# Readers who need the full list or the full text of a cut body use
# github_pr_view(include_comments=True) — which _FULL_TEXT_HINT names in the
# output whenever either cap actually fires.
_MAX_FEEDBACK_ITEMS = 20
_MAX_LINES_PER_COMMENT = 10

_FULL_TEXT_HINT = "Full comment text: github_pr_view(include_comments=True)"

# Feedback sections whose unavailability makes the merge/review verdict
# undeterminable: "threads" (unresolved threads + changes_requested) and
# "alerts" (code-scanning) both feed blocks_merge. A "comments"-only failure
# never blocks and is not counted here.
_BLOCKING_RELEVANT_SECTIONS = frozenset({"threads", "alerts"})


def _truncate_body(body: str) -> str:
    """Truncate a comment body at `_MAX_LINES_PER_COMMENT` lines.

    Returns:
        The body, truncated with a "... (truncated: showing X of Y lines)"
        marker if too long.
    """
    lines = body.splitlines()
    if len(lines) <= _MAX_LINES_PER_COMMENT:
        return body
    return "\n".join(lines[:_MAX_LINES_PER_COMMENT]) + (
        f"\n... (truncated: showing {_MAX_LINES_PER_COMMENT} of {len(lines)} lines)"
    )


def format_pr_feedback(feedback: PRFeedback, trusted: frozenset[str]) -> str:
    """Render a `PRFeedback` dict as a multi-line block.

    Items from untrusted authors are withheld: they get no per-item line
    (no body, login, path or ids), only a single count line. Withheld items
    never count towards the item cap or trigger the full-text hint, but the
    clean check still sees them.

    Args:
        feedback: Raw PR feedback from `PullRequestManager.get_pr_feedback`.
        trusted: Lowercased login allowlist from `get_trusted_commenters`.

    Returns:
        The empty-state affirmation when there is nothing to surface,
        otherwise a `PR Reviews:` block. No trailing newline.
    """
    all_unresolved = feedback["unresolved_threads"]
    all_comments = feedback["conversation_comments"]
    all_changes_requested = feedback["changes_requested"]
    alerts = feedback["alerts"]
    unavailable = feedback["unavailable"]
    skipped = feedback["skipped"]
    resolved_count = feedback["resolved_thread_count"]

    blocking = bool(all_unresolved or all_changes_requested or alerts)
    # `skipped` never makes a report non-clean; only alerts can be skipped.
    if not blocking and not all_comments and not unavailable:
        note = (
            f"alerts not checked: {getattr(skipped['alerts'], 'status', None)}"
            if "alerts" in skipped
            else "0 alerts"
        )
        return f"Reviews: clean (0 unresolved threads, {note})"

    def ok(
        item: ReviewThreadData | ChangesRequestedData | ConversationCommentData,
    ) -> bool:
        return is_trusted_author(item["author"], item["author_association"], trusted)

    unresolved = [t for t in all_unresolved if ok(t)]
    changes_requested = [r for r in all_changes_requested if ok(r)]
    comments = [c for c in all_comments if ok(c)]
    withheld_line = format_withheld_line(
        [
            ("thread", len(all_unresolved) - len(unresolved)),
            ("review", len(all_changes_requested) - len(changes_requested)),
            ("comment", len(all_comments) - len(comments)),
        ]
    )

    rendered: List[str] = []
    body_cut = False

    for thread in unresolved:
        path = thread.get("path", "")
        line_no = thread.get("line")
        author = thread.get("author", "")
        diff_hunk = thread.get("diff_hunk", "")
        comment_id = thread.get("comment_id", "")
        thread_id = thread.get("thread_id", "")
        raw = thread.get("body", "")
        body = _truncate_body(raw)
        body_cut = body_cut or body != raw
        indented_hunk = "\n".join(f"  {line}" for line in diff_hunk.splitlines())
        location = f"{path}:{line_no}" if line_no else path
        ids = (
            f" [comment_id={comment_id} thread_id={thread_id}]"
            if (comment_id or thread_id)
            else ""
        )
        rendered.append(
            f"[unresolved thread] {location} ({author}){ids}:\n"
            f"{indented_hunk}\n"
            f"  Comment: {body}"
        )

    for review in changes_requested:
        author = review.get("author", "")
        submitted_at = review.get("submitted_at")
        suffix = f" ({submitted_at})" if submitted_at else ""
        raw = review.get("body", "")
        body = _truncate_body(raw)
        body_cut = body_cut or body != raw
        rendered.append(f"[changes_requested] {author}{suffix}: {body}")

    for alert in alerts:
        path = alert["path"]
        line_no = alert["line"]
        location = f"{path}:{line_no}" if line_no else path
        rendered.append(
            f"[alert] [alert_number={alert['number']}] "
            f"{alert['rule_id']}: {alert['message']} @ {location}"
        )

    # Conversation comments render last: they never drain, so ahead of the
    # verdict-bearing sections they would starve alerts under the shared cap.
    for comment in comments:
        author = comment.get("author", "")
        raw = comment.get("body", "")
        body = _truncate_body(raw)
        body_cut = body_cut or body != raw
        rendered.append(f"[comment] {author}:\n  {body}")

    total = len(rendered)
    cap_fired = total > _MAX_FEEDBACK_ITEMS
    if cap_fired:
        kept = rendered[:_MAX_FEEDBACK_ITEMS]
        kept.append(
            f"... and {total - _MAX_FEEDBACK_ITEMS} more of {total} items "
            f"— full list via github_pr_view(include_comments=True)"
        )
        rendered = kept

    lines: List[str] = ["PR Reviews:"]
    if withheld_line:
        lines.append(withheld_line)
    lines.extend(rendered)

    for section, exc in unavailable.items():
        lines.append(f"[unavailable] {section}: {render_exception_for_display(exc)}")

    for section, exc in skipped.items():
        lines.append(
            f"[skipped] {section} not checked ({getattr(exc, 'status', None)})"
        )

    if resolved_count > 0:
        lines.append(f"{resolved_count} resolved threads")

    if body_cut or cap_fired:
        lines.append(_FULL_TEXT_HINT)

    return "\n".join(lines)


def collect_pr_feedback(
    pr_manager: PullRequestManager, pr_number: int, trusted: frozenset[str]
) -> Tuple[Optional[str], bool, bool]:
    """Fetch PR feedback for a pull request.

    Args:
        pr_manager: Manager used to fetch the feedback.
        pr_number: Pull request number.
        trusted: Lowercased login allowlist; only affects the rendered text,
            never ``blocks_merge`` or ``undeterminable``.

    Returns:
        Tuple of (formatted_text, blocks_merge, undeterminable).
        ``undeterminable`` is True when a blocking-relevant feedback section
        (``threads`` or ``alerts``) was unavailable, so a False
        ``blocks_merge`` cannot be trusted as a clean verdict and callers must
        surface UNKNOWN rather than fail open. On total failure returns
        (None, False, True) (logged at debug level).
    """
    try:
        feedback = pr_manager.get_pr_feedback(pr_number)
        text = format_pr_feedback(feedback, trusted)
        blocks_merge = bool(
            feedback["unresolved_threads"]
            or feedback["changes_requested"]
            or feedback["alerts"]
        )
        undeterminable = bool(
            feedback["unavailable"].keys() & _BLOCKING_RELEVANT_SECTIONS
        )
        return (text, blocks_merge, undeterminable)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("PR feedback collection failed", exc_info=True)
        return (None, False, True)
