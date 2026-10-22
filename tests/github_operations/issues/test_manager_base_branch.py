"""Tests for base_branch / base_branch_error population in IssueManager."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.issues import IssueManager

from .._issue_test_helpers import make_mock_issue, make_untrusted_issue

MALFORMED_BODY = "### Base Branch\n\nepic/x\nmore"
MALFORMED_MESSAGE = (
    "`### Base Branch` must contain only the branch name on one line; "
    "move other text to another section. First line: 'epic/x'"
)
VALID_BODY = "### Base Branch\n\nfeature/x\n"
LOGGER_NAME = "mcp_workspace.github_operations.issues.manager"
_TRUST = "mcp_workspace.github_operations.issues.base_branch_trust"
EDITOR_PATH = f"{_TRUST}.fetch_body_editor"
LOGIN_PATH = f"{_TRUST}._cached_login"
TRUSTED_COMMENTERS = "mcp_workspace.config.get_trusted_commenters"


def _issue(number: int, body: str) -> MagicMock:
    mock_issue = make_mock_issue(number)
    mock_issue.body = body
    mock_issue.pull_request = None
    return mock_issue


def _malformed_records(
    caplog: pytest.LogCaptureFixture, level: int
) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == LOGGER_NAME
        and record.levelno == level
        and "malformed base branch" in record.getMessage()
    ]


class TestGetIssueBaseBranchError:
    """get_issue surfaces a malformed Base Branch section as data."""

    def test_malformed_section_sets_error(
        self, mock_issue_manager: IssueManager
    ) -> None:
        mock_issue_manager._repository.get_issue.return_value = _issue(
            1, MALFORMED_BODY
        )

        result = mock_issue_manager.get_issue(1)

        assert result["base_branch"] is None
        assert result["base_branch_error"] == MALFORMED_MESSAGE

    @pytest.mark.parametrize(
        ("body", "expected_branch"),
        [
            ("### Base Branch\n\nfeature/x\n", "feature/x"),
            ("No section here", None),
            ("### Base Branch\n\n### Next\n", None),
        ],
        ids=["valid", "absent", "empty"],
    )
    def test_well_formed_section_has_no_error(
        self,
        mock_issue_manager: IssueManager,
        body: str,
        expected_branch: str | None,
    ) -> None:
        mock_issue_manager._repository.get_issue.return_value = _issue(1, body)

        result = mock_issue_manager.get_issue(1)

        assert result["base_branch"] == expected_branch
        assert result["base_branch_error"] is None


class TestListIssuesBaseBranchError:
    """list_issues surfaces a malformed Base Branch section as data."""

    def test_malformed_section_sets_error(
        self, mock_issue_manager: IssueManager
    ) -> None:
        mock_issue_manager._repository.get_issues.return_value = [
            _issue(1, MALFORMED_BODY)
        ]

        result = mock_issue_manager.list_issues()

        assert len(result) == 1
        assert result[0]["base_branch"] is None
        assert result[0]["base_branch_error"] == MALFORMED_MESSAGE

    def test_valid_section_has_no_error(self, mock_issue_manager: IssueManager) -> None:
        mock_issue_manager._repository.get_issues.return_value = [
            _issue(1, "### Base Branch\n\nfeature/x\n")
        ]

        result = mock_issue_manager.list_issues()

        assert result[0]["base_branch"] == "feature/x"
        assert result[0]["base_branch_error"] is None


class TestAuthorAssociation:
    """get_issue and list_issues carry the issue author's association."""

    def test_get_issue_carries_association(
        self, mock_issue_manager: IssueManager
    ) -> None:
        mock_issue = _issue(1, "")
        mock_issue.author_association = "CONTRIBUTOR"
        mock_issue_manager._repository.get_issue.return_value = mock_issue

        result = mock_issue_manager.get_issue(1)

        assert result["author_association"] == "CONTRIBUTOR"

    def test_list_issues_carries_association(
        self, mock_issue_manager: IssueManager
    ) -> None:
        mock_issue = _issue(1, "")
        mock_issue.author_association = "CONTRIBUTOR"
        mock_issue_manager._repository.get_issues.return_value = [mock_issue]

        result = mock_issue_manager.list_issues()

        assert result[0]["author_association"] == "CONTRIBUTOR"


class TestMalformedBaseBranchLogOnce:
    """The WARNING is logged once per (repo, issue, message)."""

    def test_repeat_fetch_logs_warning_once_then_debug(
        self, mock_issue_manager: IssueManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        mock_issue_manager._repository.get_issue.return_value = _issue(
            1, MALFORMED_BODY
        )

        mock_issue_manager.get_issue(1)
        mock_issue_manager.get_issue(1)

        assert len(_malformed_records(caplog, logging.WARNING)) == 1
        assert len(_malformed_records(caplog, logging.DEBUG)) == 1

    def test_different_issue_gets_its_own_warning(
        self, mock_issue_manager: IssueManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        mock_issue_manager._repository.get_issue.side_effect = [
            _issue(1, MALFORMED_BODY),
            _issue(2, MALFORMED_BODY),
        ]

        mock_issue_manager.get_issue(1)
        mock_issue_manager.get_issue(2)

        warnings = _malformed_records(caplog, logging.WARNING)
        assert len(warnings) == 2
        assert "#1" in warnings[0].getMessage()
        assert "#2" in warnings[1].getMessage()


@pytest.fixture(name="editor")
def _editor() -> Iterator[MagicMock]:
    """Patch the body-editor lookup; no editor by default."""
    with patch(EDITOR_PATH, return_value=None) as mock_editor:
        yield mock_editor


@pytest.fixture(name="token_login")
def _token_login() -> Iterator[MagicMock]:
    """Patch the token-user lookup to return "me"."""
    with patch(LOGIN_PATH, return_value="me") as mock_login:
        yield mock_login


def _fetch_one(
    manager: IssueManager, mock_issue: MagicMock, via: str
) -> tuple[Optional[str], Optional[str]]:
    """Return (base_branch, base_branch_error) for one issue via get_issue or list_issues."""
    if via == "get_issue":
        manager._repository.get_issue.return_value = mock_issue
        data = manager.get_issue(mock_issue.number)
    else:
        manager._repository.get_issues.return_value = [mock_issue]
        [data] = manager.list_issues()
    return data.get("base_branch"), data.get("base_branch_error")


@pytest.mark.usefixtures("token_login")
@pytest.mark.parametrize("via", ["get_issue", "list_issues"])
class TestUntrustedBaseBranch:
    """An untrusted body cannot choose the base branch."""

    def test_valid_section_no_editor_ignored(
        self, mock_issue_manager: IssueManager, editor: MagicMock, via: str
    ) -> None:
        result = _fetch_one(
            mock_issue_manager, make_untrusted_issue(1, VALID_BODY), via
        )

        assert result == (None, None)
        editor.assert_called_once()

    @pytest.mark.usefixtures("editor")
    def test_malformed_section_ignored_without_warning(
        self,
        mock_issue_manager: IssueManager,
        caplog: pytest.LogCaptureFixture,
        via: str,
    ) -> None:
        caplog.set_level(logging.DEBUG)

        result = _fetch_one(
            mock_issue_manager, make_untrusted_issue(1, MALFORMED_BODY), via
        )

        assert result == (None, None)
        assert not _malformed_records(caplog, logging.WARNING)
        assert not _malformed_records(caplog, logging.DEBUG)

    @pytest.mark.usefixtures("editor")
    def test_info_log_names_issue_and_author(
        self,
        mock_issue_manager: IssueManager,
        caplog: pytest.LogCaptureFixture,
        via: str,
    ) -> None:
        caplog.set_level(logging.INFO, logger=LOGGER_NAME)

        _fetch_one(mock_issue_manager, make_untrusted_issue(7, VALID_BODY), via)

        messages = [
            r.getMessage()
            for r in caplog.records
            if r.name == LOGGER_NAME and r.levelno == logging.INFO
        ]
        assert any("#7" in m and "@mallory" in m for m in messages)

    def test_token_user_editor_section_used(
        self, mock_issue_manager: IssueManager, editor: MagicMock, via: str
    ) -> None:
        editor.return_value = "Me"

        result = _fetch_one(
            mock_issue_manager, make_untrusted_issue(1, VALID_BODY), via
        )

        assert result == ("feature/x", None)

    def test_allowlisted_editor_section_used(
        self,
        mock_issue_manager: IssueManager,
        editor: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        via: str,
    ) -> None:
        monkeypatch.setattr(TRUSTED_COMMENTERS, lambda: frozenset({"bob"}))
        editor.return_value = "Bob"

        result = _fetch_one(
            mock_issue_manager, make_untrusted_issue(1, VALID_BODY), via
        )

        assert result == ("feature/x", None)

    def test_untrusted_editor_ignored(
        self, mock_issue_manager: IssueManager, editor: MagicMock, via: str
    ) -> None:
        editor.return_value = "eve"

        result = _fetch_one(
            mock_issue_manager, make_untrusted_issue(1, VALID_BODY), via
        )

        assert result == (None, None)

    def test_trusted_author_skips_editor_lookup(
        self, mock_issue_manager: IssueManager, editor: MagicMock, via: str
    ) -> None:
        result = _fetch_one(mock_issue_manager, _issue(1, VALID_BODY), via)

        assert result == ("feature/x", None)
        editor.assert_not_called()

    def test_no_section_skips_editor_lookup(
        self, mock_issue_manager: IssueManager, editor: MagicMock, via: str
    ) -> None:
        result = _fetch_one(
            mock_issue_manager, make_untrusted_issue(1, "No section here"), via
        )

        assert result == (None, None)
        editor.assert_not_called()

    def test_trusted_author_invalid_ref_sets_error(
        self, mock_issue_manager: IssueManager, via: str
    ) -> None:
        branch, error = _fetch_one(
            mock_issue_manager, _issue(1, "### Base Branch\n\nmain branch\n"), via
        )

        assert branch is None
        assert error is not None
        assert "must be a valid git branch name" in error
        assert "'main branch'" in error


@contextmanager
def _failing_graphql(manager: IssueManager) -> Iterator[MagicMock]:
    """Make the manager's GraphQL requests raise a GithubException."""
    requester = manager._github_client._Github__requester  # type: ignore[attr-defined]  # pylint: disable=protected-access
    with patch.object(
        requester,
        "graphql_query",
        side_effect=GithubException(500, {"message": "boom"}, None),
    ) as graphql_query:
        yield graphql_query


class TestBaseBranchTrustFailures:
    """Lookup failures mean "untrusted" and never abort the call."""

    def test_list_issues_graphql_failure_ignores_section(
        self, mock_issue_manager: IssueManager
    ) -> None:
        mock_issue_manager._repository.get_issues.return_value = [
            make_untrusted_issue(1, VALID_BODY),
            make_untrusted_issue(2, VALID_BODY),
        ]

        with _failing_graphql(mock_issue_manager) as graphql_query:
            result = mock_issue_manager.list_issues()

        assert graphql_query.call_count == 2

        assert [d["number"] for d in result] == [1, 2]
        assert all(d["base_branch"] is None for d in result)
        assert all(d["base_branch_error"] is None for d in result)

    def test_get_issue_graphql_failure_returns_issue(
        self, mock_issue_manager: IssueManager
    ) -> None:
        mock_issue_manager._repository.get_issue.return_value = make_untrusted_issue(
            3, VALID_BODY
        )

        with _failing_graphql(mock_issue_manager) as graphql_query:
            result = mock_issue_manager.get_issue(3)

        graphql_query.assert_called_once()
        assert result["number"] == 3
        assert result["base_branch"] is None
        assert result["base_branch_error"] is None

    def test_get_issue_cached_login_failure_ignores_section(
        self, mock_issue_manager: IssueManager
    ) -> None:
        mock_issue_manager._repository.get_issue.return_value = make_untrusted_issue(
            3, VALID_BODY
        )
        with (
            patch(EDITOR_PATH, return_value="me"),
            patch(LOGIN_PATH, side_effect=GithubException(401, {"message": "x"}, None)),
        ):
            result = mock_issue_manager.get_issue(3)

        assert result["number"] == 3
        assert result["base_branch"] is None
        assert result["base_branch_error"] is None


@pytest.mark.usefixtures("editor", "token_login")
class TestAllowlistLaziness:
    """The allowlist is read at most once per call, and only when needed."""

    def test_untrusted_issues_read_allowlist_once(
        self, mock_issue_manager: IssueManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        allowlist = MagicMock(return_value=frozenset())
        monkeypatch.setattr(TRUSTED_COMMENTERS, allowlist)
        mock_issue_manager._repository.get_issues.return_value = [
            make_untrusted_issue(n, VALID_BODY) for n in (1, 2, 3)
        ]

        result = mock_issue_manager.list_issues()

        assert len(result) == 3
        allowlist.assert_called_once_with()

    def test_trusted_issues_never_read_allowlist(
        self, mock_issue_manager: IssueManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        allowlist = MagicMock(return_value=frozenset())
        monkeypatch.setattr(TRUSTED_COMMENTERS, allowlist)
        mock_issue_manager._repository.get_issues.return_value = [
            _issue(n, VALID_BODY) for n in (1, 2, 3)
        ]

        result = mock_issue_manager.list_issues()

        assert [d["base_branch"] for d in result] == ["feature/x"] * 3
        allowlist.assert_not_called()
