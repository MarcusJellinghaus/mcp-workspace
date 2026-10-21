"""Tests for base_branch / base_branch_error population in IssueManager."""

import logging
from unittest.mock import MagicMock

import pytest

from mcp_workspace.github_operations.issues import IssueManager

from .._issue_test_helpers import make_mock_issue

MALFORMED_BODY = "### Base Branch\n\nepic/x\nmore"
MALFORMED_MESSAGE = (
    "`### Base Branch` must contain only the branch name on one line; "
    "move other text to another section. First line: 'epic/x'"
)
LOGGER_NAME = "mcp_workspace.github_operations.issues.manager"


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
