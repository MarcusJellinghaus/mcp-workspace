"""Tests for the ``github_issue_edit`` MCP tool in server.py.

``edit_issue`` has no transaction, so failure can reach the tool through two
channels — the empty-``IssueData`` sentinel and a re-raised exception. Both must
end on the warn-and-report path rather than as a bare ``Error:`` after a write
that partially landed.
"""

from pathlib import Path
from typing import Any, Callable, Generator
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from mcp_workspace import server as server_module
from mcp_workspace.github_operations.base_manager import IssueIdentityMismatchError
from mcp_workspace.github_operations.issues.types import (
    IssueData,
    create_empty_issue_data,
)
from mcp_workspace.server import github_issue_edit, set_project_dir


@pytest.fixture(autouse=True)
def setup_server(project_dir: Path) -> Generator[None, None, None]:
    """Setup the server with the project directory."""
    set_project_dir(project_dir)
    yield


@pytest.fixture(autouse=True)
def reset_login_cache() -> Generator[None, None, None]:
    """Clear the cached '@me' login so tests never leak it into each other."""
    server_module._login_cache.clear()
    yield
    server_module._login_cache.clear()


def _make_issue(
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
        labels=labels or [],
        assignees=assignees or [],
        user="alice",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-02T00:00:00",
        url="https://github.com/test/repo/issues/42",
        locked=False,
    )


def _label(name: str) -> dict[str, str]:
    """Create a LabelData-shaped dict for testing."""
    return {"name": name, "color": "d73a4a", "description": "", "url": ""}


def _make_manager(
    issue: IssueData | None = None,
    available_labels: list[dict[str, str]] | None = None,
    login: str = "marcus",
) -> MagicMock:
    """Create a mocked IssueManager with the calls the tool makes."""
    mock_mgr = MagicMock()
    mock_mgr.edit_issue.return_value = issue if issue is not None else _make_issue()
    mock_mgr.get_available_labels.return_value = available_labels or []
    mock_mgr._github_client.get_user.return_value.login = login
    return mock_mgr


def _recording_edit_issue(
    writes: list[str],
    result: IssueData | None = None,
    error: Exception | None = None,
) -> Callable[..., IssueData]:
    """Build an ``edit_issue`` side effect that logs writes like the real one.

    The real ``edit_issue`` appends to ``attempted_writes`` before issuing each
    write call, so a mock standing in for a mid-sequence failure must do the
    same — that log is how the tool tells a failed opening fetch from a write
    that may already have landed.

    Args:
        writes: Entries the stand-in records before failing or returning.
        result: IssueData to return; defaults to the empty sentinel.
        error: Exception to raise instead of returning, if any.

    Returns:
        A callable suitable for ``mock_mgr.edit_issue.side_effect``.
    """

    def _side_effect(_number: int, **kwargs: Any) -> IssueData:
        attempted = kwargs.get("attempted_writes")
        if attempted is not None:
            attempted.extend(writes)
        if error is not None:
            raise error
        return result if result is not None else create_empty_issue_data()

    return _side_effect


def _line_starting(result: str, prefix: str) -> str:
    """Return the single result line starting with prefix."""
    matches = [line for line in result.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1, f"expected one {prefix!r} line in:\n{result}"
    return matches[0]


# =============================================================================
# Success path
# =============================================================================


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_happy_path(mock_manager_cls: MagicMock) -> None:
    """Reports the resulting issue, labels and assignees in three lines."""
    mock_manager_cls.return_value = _make_manager(
        issue=_make_issue(labels=["bug", "enhancement"], assignees=["alice"]),
        available_labels=[_label("bug"), _label("enhancement")],
    )

    result = github_issue_edit(number=42, title="New title")

    assert result.splitlines() == [
        "Updated issue #42 — https://github.com/test/repo/issues/42 (state: open)",
        "Labels: bug, enhancement",
        "Assignees: alice",
    ]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_empty_collections_render_none(
    mock_manager_cls: MagicMock,
) -> None:
    """Empty label and assignee sets render as '(none)', not as blanks."""
    mock_manager_cls.return_value = _make_manager(issue=_make_issue())

    result = github_issue_edit(number=42, body="New body")

    assert "Labels: (none)" in result
    assert "Assignees: (none)" in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_forwards_arguments(mock_manager_cls: MagicMock) -> None:
    """Every requested argument reaches edit_issue."""
    mock_mgr = _make_manager(
        issue=_make_issue(state="closed", labels=["bug"], assignees=["alice"]),
        available_labels=[_label("bug")],
    )
    mock_manager_cls.return_value = mock_mgr

    github_issue_edit(
        number=42,
        title="New title",
        body="New body",
        add_labels=["bug"],
        remove_labels=["wontfix"],
        add_assignees=["alice"],
        state="closed",
    )

    args, kwargs = mock_mgr.edit_issue.call_args
    assert args[0] == 42
    assert kwargs["title"] == "New title"
    assert kwargs["body"] == "New body"
    assert kwargs["add_labels"] == ["bug"]
    assert kwargs["remove_labels"] == ["wontfix"]
    assert kwargs["add_assignees"] == ["alice"]
    assert kwargs["state"] == "closed"


# =============================================================================
# Partial writes — both failure channels
# =============================================================================


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_sentinel_channel_warns_and_reports(
    mock_manager_cls: MagicMock,
) -> None:
    """A swallowed API error still reports the resulting state behind a warning."""
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit_issue(["scalars"])
    mock_mgr.get_issue.return_value = _make_issue(title="New title")
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, title="New title")

    assert result.startswith("Warning:")
    assert (
        "Updated issue #42 — https://github.com/test/repo/issues/42 (state: open)"
        in result
    )
    mock_mgr.get_issue.assert_called_once_with(42)


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_exception_channel_warns_and_reports(
    mock_manager_cls: MagicMock,
) -> None:
    """A re-raised 403 mid-sequence is a partial write, never a bare error."""
    mock_mgr = _make_manager(available_labels=[_label("bug")])
    mock_mgr.edit_issue.side_effect = _recording_edit_issue(
        ["scalars", "add_labels"],
        error=GithubException(
            403, {"message": "Resource not accessible by integration"}, None
        ),
    )
    # The title landed before the label add was rejected
    mock_mgr.get_issue.return_value = _make_issue(title="New title", labels=[])
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, title="New title", add_labels=["bug"])

    assert result.startswith("Warning:")
    assert not result.startswith("Error:")
    assert "403" in result.splitlines()[0]
    assert _line_starting(result, "Applied:") == "Applied: title"
    assert _line_starting(result, "Not applied:") == "Not applied: add_labels"
    assert (
        "Updated issue #42 — https://github.com/test/repo/issues/42 (state: open)"
        in result
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_value_error_channel_warns_and_reports(
    mock_manager_cls: MagicMock,
) -> None:
    """An IssueIdentityMismatchError from the closing refetch is a partial write."""
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit_issue(
        ["scalars"],
        error=IssueIdentityMismatchError(
            "Issue #42 belongs to other/repo, not test/repo"
        ),
    )
    mock_mgr.get_issue.return_value = _make_issue(title="New title")
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, title="New title")

    assert result.startswith("Warning:")
    assert "other/repo" in result
    assert _line_starting(result, "Applied:") == "Applied: title"
    assert (
        "Updated issue #42 — https://github.com/test/repo/issues/42 (state: open)"
        in result
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_reports_only_requested_arguments(
    mock_manager_cls: MagicMock,
) -> None:
    """Arguments the caller never passed appear in neither Applied nor Not applied."""
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit_issue(["scalars"])
    mock_mgr.get_issue.return_value = _make_issue(title="New title")
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, title="New title")

    assert _line_starting(result, "Applied:") == "Applied: title"
    assert _line_starting(result, "Not applied:") == "Not applied: (none)"
    assert "add_labels" not in result
    assert "remove_labels" not in result
    assert "add_assignees" not in result
    assert "body" not in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_case_differing_label_counts_as_applied(
    mock_manager_cls: MagicMock,
) -> None:
    """A label that landed under the repository's casing is Applied, not missing.

    _check_labels accepts "Bug" for the repository's "bug", and GitHub attaches
    "bug", so an exact-match comparison against the refetched set would report a
    change that did land as "Not applied".
    """
    mock_mgr = _make_manager(available_labels=[_label("bug"), _label("wontfix")])
    mock_mgr.edit_issue.side_effect = _recording_edit_issue(
        ["add_labels", "remove_labels"]
    )
    mock_mgr.get_issue.return_value = _make_issue(labels=["bug"])
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, add_labels=["Bug"], remove_labels=["WontFix"])

    assert _line_starting(result, "Applied:") == "Applied: add_labels, remove_labels"
    assert _line_starting(result, "Not applied:") == "Not applied: (none)"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_case_differing_assignee_counts_as_applied(
    mock_manager_cls: MagicMock,
) -> None:
    """An assignee that landed under GitHub's canonical casing is Applied.

    GitHub matches logins case-insensitively and the refetch returns the
    canonical spelling, so an exact-match comparison would report an assignment
    that did land as "Not applied".
    """
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit_issue(["add_assignees"])
    mock_mgr.get_issue.return_value = _make_issue(assignees=["MarcusJellinghaus"])
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, add_assignees=["marcusjellinghaus"])

    assert _line_starting(result, "Applied:") == "Applied: add_assignees"
    assert _line_starting(result, "Not applied:") == "Not applied: (none)"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_body_differing_only_in_line_endings_is_applied(
    mock_manager_cls: MagicMock,
) -> None:
    """A body GitHub stored with normalised newlines still counts as Applied."""
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit_issue(["scalars"])
    mock_mgr.get_issue.return_value = _make_issue(body="line one\nline two\n")
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, body="line one\r\nline two\r\n")

    assert _line_starting(result, "Applied:") == "Applied: body"
    assert _line_starting(result, "Not applied:") == "Not applied: (none)"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_title_differing_only_in_whitespace_is_applied(
    mock_manager_cls: MagicMock,
) -> None:
    """A title stored without its surrounding whitespace still counts as Applied.

    edit_issue strips the title before writing it, exactly as create_issue
    does, so a byte-for-byte comparison against the request would report a
    title edit that landed as "Not applied".
    """
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit_issue(["scalars"])
    mock_mgr.get_issue.return_value = _make_issue(title="New title")
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, title="  New title  ")

    assert _line_starting(result, "Applied:") == "Applied: title"
    assert _line_starting(result, "Not applied:") == "Not applied: (none)"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_failure_before_any_write_does_not_claim_an_update(
    mock_manager_cls: MagicMock,
) -> None:
    """No write was logged, so the readable issue is current state, not an update.

    The opening fetch failed, so nothing can have been applied: calling this a
    partial failure or reporting the issue as "Updated" would both be false.
    """
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit_issue([])
    mock_mgr.get_issue.return_value = _make_issue(title="Old title", labels=["bug"])
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, title="New title")

    assert result.startswith("Error: edit of issue #42 failed")
    assert "no changes were made" in result
    assert "Warning" not in result
    assert "Updated issue" not in result
    assert "Applied:" not in result
    # The resulting state is still reported, just not as an update
    assert "Issue #42 — https://github.com/test/repo/issues/42 (state: open)" in result
    assert "Labels: bug" in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_unreadable_issue_reports_not_found(
    mock_manager_cls: MagicMock,
) -> None:
    """No write was logged and the issue is unreadable: the opening fetch 404ed.

    Saying "edit failed" would imply a partial write that cannot have happened,
    because edit_issue never issued a write call.
    """
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit_issue([])
    mock_mgr.get_issue.return_value = create_empty_issue_data()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, title="New title")

    assert result.startswith("Error: issue #42 not found or not accessible")
    assert result.endswith("no changes were made")
    assert "Warning" not in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_swallowed_mid_sequence_failure_is_indeterminate(
    mock_manager_cls: MagicMock,
) -> None:
    """A logged write plus an unreadable refetch must not claim nothing changed.

    The scalar edit went out before the swallowed failure, so the tool cannot
    know whether it landed — it names the writes it issued instead of asserting
    an outcome it has no evidence for.
    """
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit_issue(["scalars", "add_labels"])
    mock_mgr.get_available_labels.return_value = [_label("bug")]
    # The refetch is swallowed too, so the resulting state cannot be read
    mock_mgr.get_issue.return_value = create_empty_issue_data()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, title="New title", add_labels=["bug"])

    assert result.startswith("Error:")
    assert "no changes were made" not in result
    assert "may or may not have been applied: scalars, add_labels" in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_raised_failure_keeps_partial_write_wording(
    mock_manager_cls: MagicMock,
) -> None:
    """A re-raised error can arrive after a write landed, so stay non-committal."""
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit_issue(
        ["scalars"],
        error=GithubException(
            403, {"message": "Resource not accessible by integration"}, None
        ),
    )
    mock_mgr.get_issue.return_value = create_empty_issue_data()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, title="New title")

    assert result.startswith("Error:")
    assert "could not be re-read" in result
    assert "no changes were made" not in result
    assert "may or may not have been applied: scalars" in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_failed_refetch_names_both_failures(
    mock_manager_cls: MagicMock,
) -> None:
    """A raising refetch is reported alongside the original failure reason."""
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit_issue(
        ["scalars"],
        error=GithubException(
            403, {"message": "Resource not accessible by integration"}, None
        ),
    )
    mock_mgr.get_issue.side_effect = GithubException(
        500, {"message": "Internal Server Error"}, None
    )
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, title="New title")

    assert result.startswith("Error:")
    assert "Warning" not in result
    assert "403" in result
    assert "500" in result
    assert "may or may not have been applied: scalars" in result


# =============================================================================
# Label guards
# =============================================================================


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_rejects_status_label_on_add_side(
    mock_manager_cls: MagicMock,
) -> None:
    """A status-* label cannot be added through this tool."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, add_labels=["status-04:in-progress"])

    assert result.startswith("Error:")
    assert "status-04:in-progress" in result
    assert "set-status" in result
    mock_mgr.edit_issue.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_rejects_status_label_on_remove_side(
    mock_manager_cls: MagicMock,
) -> None:
    """Removing a status-* label would leave zero — also rejected."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, remove_labels=["status-04:in-progress"])

    assert result.startswith("Error:")
    assert "status-04:in-progress" in result
    assert "set-status" in result
    mock_mgr.edit_issue.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_rejects_differently_cased_status_label(
    mock_manager_cls: MagicMock,
) -> None:
    """The remove side has no known-label check, so the guard must ignore case."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, remove_labels=["Status-04:in-progress"])

    assert result.startswith("Error:")
    assert "set-status" in result
    mock_mgr.edit_issue.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_accepts_differently_cased_label(
    mock_manager_cls: MagicMock,
) -> None:
    """GitHub label names are case-insensitive, so 'Bug' is a valid add."""
    mock_mgr = _make_manager(
        issue=_make_issue(labels=["bug"]), available_labels=[_label("bug")]
    )
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, add_labels=["Bug"])

    assert result.startswith("Updated issue #42")
    assert mock_mgr.edit_issue.call_args.kwargs["add_labels"] == ["Bug"]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_rejects_unknown_add_label(
    mock_manager_cls: MagicMock,
) -> None:
    """A typo in an added label is rejected rather than creating the label."""
    mock_mgr = _make_manager(available_labels=[_label("bug")])
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, add_labels=["bugg"])

    assert result == "Error: unknown label(s): bugg"
    mock_mgr.edit_issue.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_label_lookup_failure_is_not_unknown_label(
    mock_manager_cls: MagicMock,
) -> None:
    """A failed label lookup reports the API error, never 'unknown label'."""
    mock_mgr = _make_manager()
    mock_mgr.get_available_labels.side_effect = GithubException(
        500, {"message": "Internal Server Error"}, None
    )
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, add_labels=["bug"])

    assert result.startswith("Error:")
    assert "500" in result
    assert "unknown label" not in result
    mock_mgr.edit_issue.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_remove_only_skips_label_lookup(
    mock_manager_cls: MagicMock,
) -> None:
    """With an empty add side there is nothing to validate — no API call."""
    mock_mgr = _make_manager(issue=_make_issue(labels=[]))
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, remove_labels=["wontfix"])

    assert result.startswith("Updated issue #42")
    mock_mgr.get_available_labels.assert_not_called()


# =============================================================================
# Assignees and pre-write validation
# =============================================================================


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_resolves_me_assignee(mock_manager_cls: MagicMock) -> None:
    """'@me' is resolved to the authenticated login before the write."""
    mock_mgr = _make_manager(issue=_make_issue(assignees=["marcus"]), login="marcus")
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, add_assignees=["@me"])

    assert result.startswith("Updated issue #42")
    assert mock_mgr.edit_issue.call_args.kwargs["add_assignees"] == ["marcus"]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_rejects_bad_state_before_writing(
    mock_manager_cls: MagicMock,
) -> None:
    """An invalid state is caught before any API call, so it is a plain error."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, state="bogus")

    assert result.startswith("Error:")
    assert "Warning" not in result
    mock_mgr.edit_issue.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_rejects_invalid_number_before_writing(
    mock_manager_cls: MagicMock,
) -> None:
    """An invalid issue number is caught before any API call."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=0, title="New title")

    assert result.startswith("Error:")
    assert "Warning" not in result
    mock_mgr.edit_issue.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_issue_edit_rejects_empty_title_before_writing(
    mock_manager_cls: MagicMock,
) -> None:
    """GitHub rejects an empty title, so catch it before anything is written.

    Reaching the API would turn a caller mistake into a partial-write warning.
    """
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = github_issue_edit(number=42, title="   ")

    assert result == "Error: Issue title cannot be empty"
    mock_mgr.edit_issue.assert_not_called()
