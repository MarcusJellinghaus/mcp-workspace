"""Workflow status transitions for issues.

A status is a ``status-*`` label. ``set_issue_status`` validates the target
against the repo's label cache, replaces every status label on the issue with
it, and returns the user-facing result text for every outcome.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from ..caching.labels import get_cached_labels
from ..labels_manager import LabelData
from .cache import set_issue_labels_in_cache

if TYPE_CHECKING:
    from .manager import IssueManager

STATUS_LABEL_PREFIX = "status-"


def is_status_label(name: str) -> bool:
    """Return True if ``name`` is a workflow status label (case-insensitive)."""
    return name.casefold().startswith(STATUS_LABEL_PREFIX)


def _invalid(value: str, known: Iterable[LabelData], footer: str) -> str:
    """Build the text for a status value that is not a cached status label."""
    lines = [f"{label['name']}  {label['description']}".rstrip() for label in known]
    available = "\n".join(lines) if lines else "(none)"
    return f'Label "{value}" not found. Available status labels:\n{available}\n{footer}'


def set_issue_status(
    manager: IssueManager,
    number: int,
    status: str,
    from_status: str | None = None,
    refresh_labels: bool = False,
) -> str:
    """Move an issue to ``status``; return the user-facing result text.

    Args:
        manager: Issue manager of the issue's repository.
        number: Issue number.
        status: Target status label, matched case-insensitively.
        from_status: Only change when the issue's sole status is this label.
        refresh_labels: Refetch the repo's labels before validating.

    Returns:
        The result text: invalid label, guard failed, no-op, changed or
        unconfirmed write. Ends with a note when the issue is closed.
    """  # noqa: DOC502  # label-cache and issue-read errors propagate unchanged
    labels, footer = get_cached_labels(manager, refresh=refresh_labels)
    known = {
        label["name"].casefold(): label
        for label in labels
        if is_status_label(label["name"])
    }
    for value in [status] + ([from_status] if from_status is not None else []):
        if value.casefold() not in known:
            return _invalid(value, known.values(), footer)
    target = known[status.casefold()]["name"]

    issue = manager.get_issue_for_status(number)
    current = [name for name in issue["labels"] if is_status_label(name)]
    current_folded = [name.casefold() for name in current]
    old = ", ".join(current) or "<none>"
    note = f"\nNote: issue #{number} is closed." if issue["state"] == "closed" else ""

    if from_status is not None and current_folded != [from_status.casefold()]:
        return (
            f"Status of issue #{number} not changed: current status is {old}, "
            f"not {from_status}.{note}"
        )
    if current_folded == [target.casefold()]:
        return f"Issue #{number} already has status {target}; nothing changed.{note}"

    keep = [name for name in issue["labels"] if not is_status_label(name)]
    result = manager.set_labels(number, *keep, target)
    if result["number"] == 0:
        return (
            f"Error: write to issue #{number} failed or unconfirmed — "
            f"re-check with github_issue_view{note}"
        )

    set_issue_labels_in_cache(manager.repo_identifier, number, result["labels"])
    return (
        f"Issue #{number} status: {old} → {target}\n"
        f"Labels: {', '.join(result['labels']) or '(none)'}{note}"
    )
