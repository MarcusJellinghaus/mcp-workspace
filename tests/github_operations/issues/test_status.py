"""Tests for set_issue_status and is_status_label."""

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from mcp_workspace.github_operations.caching.labels import CachedLabels
from mcp_workspace.github_operations.issues.status import (
    is_status_label,
    set_issue_status,
)
from mcp_workspace.github_operations.labels_manager import LabelData
from mcp_workspace.utils.repo_identifier import RepoIdentifier

_STATUS = "mcp_workspace.github_operations.issues.status"
_REPO = RepoIdentifier("owner", "repo")
_FOOTER = "Label cache last updated 2026-01-01T00:00:00Z"


def _label(name: str, description: str = "") -> LabelData:
    """Build a cached LabelData entry."""
    return LabelData(name=name, color="ffffff", description=description, url="")


_CACHED = [
    _label("status-01:created", "Fresh issue"),
    _label("status-03:foo", "Foo step"),
    _label("status-05:bar"),
    _label("bug", "Something broken"),
]


def _issue(labels: list[str], number: int = 7, state: str = "open") -> dict[str, Any]:
    """Build a minimal IssueData-like dict."""
    return {"number": number, "state": state, "labels": labels}


@pytest.fixture(name="manager")
def _manager() -> MagicMock:
    """Manager mock with a repo identifier."""
    manager = MagicMock()
    manager.repo_identifier = _REPO
    return manager


@pytest.fixture(name="cache_write")
def _cache_write() -> Iterator[MagicMock]:
    """Patch the coordinator cache write."""
    with patch(f"{_STATUS}.set_issue_labels_in_cache") as mock:
        yield mock


@pytest.fixture(name="cached_labels", autouse=True)
def _cached_labels() -> Iterator[MagicMock]:
    """Patch the label cache read."""
    with patch(
        f"{_STATUS}.get_cached_labels", return_value=CachedLabels(_CACHED, _FOOTER)
    ) as mock:
        yield mock


class TestIsStatusLabel:
    """Tests for is_status_label."""

    def test_matches_prefix_case_insensitively(self) -> None:
        assert is_status_label("status-01:created")
        assert is_status_label("Status-01:created")
        assert not is_status_label("bug")
        assert not is_status_label("my-status-01")


class TestInvalidStatus:
    """Unknown status values are rejected before any issue read."""

    @pytest.mark.parametrize("value", ["2", "bug"])
    def test_unknown_status(
        self, manager: MagicMock, cache_write: MagicMock, value: str
    ) -> None:
        result = set_issue_status(manager, 7, value)

        assert result == (
            f'Label "{value}" not found. Available status labels:\n'
            "status-01:created  Fresh issue\n"
            "status-03:foo  Foo step\n"
            "status-05:bar\n"
            f"{_FOOTER}"
        )
        manager.get_issue_for_status.assert_not_called()
        manager.set_labels.assert_not_called()
        cache_write.assert_not_called()

    def test_unknown_from_status(self, manager: MagicMock) -> None:
        result = set_issue_status(manager, 7, "status-03:foo", from_status="nope")

        assert result.startswith('Label "nope" not found.')
        manager.get_issue_for_status.assert_not_called()
        manager.set_labels.assert_not_called()

    def test_no_status_labels_cached(
        self, manager: MagicMock, cached_labels: MagicMock
    ) -> None:
        cached_labels.return_value = CachedLabels([_label("bug")], _FOOTER)

        result = set_issue_status(manager, 7, "status-01:created")

        assert result == (
            'Label "status-01:created" not found. Available status labels:\n'
            f"(none)\n{_FOOTER}"
        )

    def test_refresh_labels_passed_through(
        self, manager: MagicMock, cached_labels: MagicMock
    ) -> None:
        set_issue_status(manager, 7, "2", refresh_labels=True)

        cached_labels.assert_called_once_with(manager, refresh=True)


class TestChange:
    """Successful transitions."""

    def test_case_insensitive_match_uses_repo_spelling(
        self, manager: MagicMock, cache_write: MagicMock
    ) -> None:
        manager.get_issue_for_status.return_value = _issue(["status-01:created"])
        manager.set_labels.return_value = _issue(["status-03:foo"])

        set_issue_status(manager, 7, "STATUS-03:Foo")

        manager.set_labels.assert_called_once_with(7, "status-03:foo")

    def test_removes_other_status_labels_keeps_others(
        self, manager: MagicMock, cache_write: MagicMock
    ) -> None:
        manager.get_issue_for_status.return_value = _issue(
            ["bug", "status-01:created", "Status-05:bar", "help"]
        )
        manager.set_labels.return_value = _issue(["bug", "help", "status-03:foo"])

        set_issue_status(manager, 7, "status-03:foo")

        manager.set_labels.assert_called_once_with(7, "bug", "help", "status-03:foo")

    def test_result_shows_old_new_and_returned_labels(
        self, manager: MagicMock, cache_write: MagicMock
    ) -> None:
        manager.get_issue_for_status.return_value = _issue(["bug", "status-01:created"])
        manager.set_labels.return_value = _issue(["bug", "extra", "status-03:foo"])

        result = set_issue_status(manager, 7, "status-03:foo")

        assert result == (
            "Issue #7 status: status-01:created → status-03:foo\n"
            "Labels: bug, extra, status-03:foo"
        )

    def test_no_previous_status(
        self, manager: MagicMock, cache_write: MagicMock
    ) -> None:
        manager.get_issue_for_status.return_value = _issue([])
        manager.set_labels.return_value = _issue(["status-03:foo"])

        result = set_issue_status(manager, 7, "status-03:foo")

        assert result == (
            "Issue #7 status: <none> → status-03:foo\nLabels: status-03:foo"
        )

    def test_returned_labels_empty(
        self, manager: MagicMock, cache_write: MagicMock
    ) -> None:
        manager.get_issue_for_status.return_value = _issue([])
        manager.set_labels.return_value = _issue([])

        result = set_issue_status(manager, 7, "status-03:foo")

        assert result.endswith("\nLabels: (none)")

    def test_success_updates_coordinator_cache(
        self, manager: MagicMock, cache_write: MagicMock
    ) -> None:
        manager.get_issue_for_status.return_value = _issue(["status-01:created"])
        manager.set_labels.return_value = _issue(["status-03:foo", "x"])

        set_issue_status(manager, 7, "status-03:foo")

        cache_write.assert_called_once_with(_REPO, 7, ["status-03:foo", "x"])

    def test_closed_issue_gets_note(
        self, manager: MagicMock, cache_write: MagicMock
    ) -> None:
        manager.get_issue_for_status.return_value = _issue(
            ["status-01:created"], state="closed"
        )
        manager.set_labels.return_value = _issue(["status-03:foo"], state="closed")

        result = set_issue_status(manager, 7, "status-03:foo")

        assert result == (
            "Issue #7 status: status-01:created → status-03:foo\n"
            "Labels: status-03:foo\n"
            "Note: issue #7 is closed."
        )

    def test_target_plus_other_status_is_written(
        self, manager: MagicMock, cache_write: MagicMock
    ) -> None:
        manager.get_issue_for_status.return_value = _issue(
            ["status-03:foo", "status-05:bar"]
        )
        manager.set_labels.return_value = _issue(["status-03:foo"])

        result = set_issue_status(manager, 7, "status-03:foo")

        manager.set_labels.assert_called_once_with(7, "status-03:foo")
        assert result.startswith(
            "Issue #7 status: status-03:foo, status-05:bar → status-03:foo\n"
        )


class TestNoOp:
    """Issue already in the target status."""

    def test_already_in_target(
        self, manager: MagicMock, cache_write: MagicMock
    ) -> None:
        manager.get_issue_for_status.return_value = _issue(["bug", "Status-03:Foo"])

        result = set_issue_status(manager, 7, "status-03:foo")

        assert result == "Issue #7 already has status status-03:foo; nothing changed."
        manager.set_labels.assert_not_called()
        cache_write.assert_not_called()

    def test_closed_note_on_no_op(self, manager: MagicMock) -> None:
        manager.get_issue_for_status.return_value = _issue(
            ["status-03:foo"], state="closed"
        )

        result = set_issue_status(manager, 7, "status-03:foo")

        assert result == (
            "Issue #7 already has status status-03:foo; nothing changed.\n"
            "Note: issue #7 is closed."
        )


class TestGuard:
    """from_status guard."""

    def test_mismatch_reports_actual_status(
        self, manager: MagicMock, cache_write: MagicMock
    ) -> None:
        manager.get_issue_for_status.return_value = _issue(["status-05:bar"])

        result = set_issue_status(
            manager, 7, "status-03:foo", from_status="status-01:created"
        )

        assert result == (
            "Status of issue #7 not changed: current status is status-05:bar, "
            "not status-01:created."
        )
        manager.set_labels.assert_not_called()
        cache_write.assert_not_called()

    def test_mismatch_no_status(self, manager: MagicMock) -> None:
        manager.get_issue_for_status.return_value = _issue(["bug"])

        result = set_issue_status(
            manager, 7, "status-03:foo", from_status="status-01:created"
        )

        assert result == (
            "Status of issue #7 not changed: current status is <none>, "
            "not status-01:created."
        )
        manager.set_labels.assert_not_called()

    def test_several_status_labels_fail_guard(self, manager: MagicMock) -> None:
        manager.get_issue_for_status.return_value = _issue(
            ["status-01:created", "status-05:bar"]
        )

        result = set_issue_status(
            manager, 7, "status-03:foo", from_status="status-01:created"
        )

        assert result == (
            "Status of issue #7 not changed: current status is "
            "status-01:created, status-05:bar, not status-01:created."
        )
        manager.set_labels.assert_not_called()

    def test_mismatch_closed_note(self, manager: MagicMock) -> None:
        manager.get_issue_for_status.return_value = _issue(
            ["status-05:bar"], state="closed"
        )

        result = set_issue_status(
            manager, 7, "status-03:foo", from_status="status-01:created"
        )

        assert result.endswith("\nNote: issue #7 is closed.")

    def test_match_writes(self, manager: MagicMock, cache_write: MagicMock) -> None:
        manager.get_issue_for_status.return_value = _issue(["status-01:created"])
        manager.set_labels.return_value = _issue(["status-03:foo"])

        result = set_issue_status(
            manager, 7, "status-03:foo", from_status="STATUS-01:created"
        )

        manager.set_labels.assert_called_once_with(7, "status-03:foo")
        assert result.startswith("Issue #7 status: status-01:created → status-03:foo")


class TestUnconfirmed:
    """set_labels returning an empty result."""

    def test_unconfirmed_write(
        self, manager: MagicMock, cache_write: MagicMock
    ) -> None:
        manager.get_issue_for_status.return_value = _issue(["status-01:created"])
        manager.set_labels.return_value = _issue([], number=0)

        result = set_issue_status(manager, 7, "status-03:foo")

        assert result == (
            "Error: write to issue #7 failed or unconfirmed — "
            "re-check with github_issue_view"
        )
        cache_write.assert_not_called()


class TestErrorsPropagate:
    """Errors from the issue read are not swallowed."""

    @pytest.mark.parametrize(
        "error",
        [
            ValueError("#7 is a pull request, not an issue"),
            GithubException(404, {"message": "Not Found"}),
        ],
    )
    def test_issue_read_error_propagates(
        self, manager: MagicMock, cache_write: MagicMock, error: Exception
    ) -> None:
        manager.get_issue_for_status.side_effect = error

        with pytest.raises(type(error)) as exc_info:
            set_issue_status(manager, 7, "status-03:foo")

        assert exc_info.value is error

        manager.set_labels.assert_not_called()
        cache_write.assert_not_called()
