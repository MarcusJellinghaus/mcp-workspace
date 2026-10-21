"""Tests for ``_resolve_base_branch`` and the ``get_base_branch`` tool.

A malformed Base Branch section on the linked issue is surfaced as an
``Error: issue #N: …`` string and never falls back to PR/merge-base/default.
"""

import logging
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.github_operations import IssueIdentityMismatchError
from mcp_workspace.server import _resolve_base_branch, get_base_branch, set_project_dir

DETECT = "mcp_workspace.git_operations.base_branch.detect_base_branch"
ISSUE_MANAGER = "mcp_workspace.github_operations.issues.IssueManager"
PR_MANAGER = "mcp_workspace.github_operations.pr_manager.PullRequestManager"
CURRENT_BRANCH = "mcp_workspace.git_operations.branch_queries.get_current_branch_name"

BRANCH = "42-some-feature"
SENTENCE = "Base Branch section has more than one branch name."


def _issue(number: int = 42, **extra: Any) -> dict[str, Any]:
    """Build a minimal IssueData-like dict."""
    data: dict[str, Any] = {"number": number, "base_branch": None}
    data.update(extra)
    return data


@pytest.fixture(autouse=True)
def setup_server(project_dir: Path) -> Generator[None, None, None]:
    """Setup the server with the project directory."""
    set_project_dir(project_dir)
    yield


class TestResolveBaseBranch:
    """Tests for the ``_resolve_base_branch`` helper."""

    def test_malformed_issue_returns_error_without_detection(
        self, tmp_path: Path
    ) -> None:
        """A malformed section yields an error and skips detection."""
        pr_manager = MagicMock()
        with (
            patch(ISSUE_MANAGER) as mock_im_cls,
            patch(DETECT) as mock_detect,
        ):
            mock_im_cls.return_value.get_issue.return_value = _issue(
                base_branch_error=SENTENCE
            )
            result = _resolve_base_branch(tmp_path, BRANCH, pr_manager)

        assert result == (None, f"Error: issue #42: {SENTENCE}")
        mock_detect.assert_not_called()
        mock_im_cls.return_value.get_issue.assert_called_once_with(42)

    def test_valid_issue_passes_issue_data_to_detection(self, tmp_path: Path) -> None:
        """A valid issue is handed to detect_base_branch once."""
        pr_manager = MagicMock()
        fetched = _issue(base_branch="develop")
        with (
            patch(ISSUE_MANAGER) as mock_im_cls,
            patch(DETECT, return_value="develop") as mock_detect,
        ):
            mock_im_cls.return_value.get_issue.return_value = fetched
            result = _resolve_base_branch(tmp_path, BRANCH, pr_manager)

        assert result == ("develop", None)
        mock_detect.assert_called_once_with(
            tmp_path, current_branch=BRANCH, issue_data=fetched, pr_manager=pr_manager
        )
        mock_im_cls.return_value.get_issue.assert_called_once_with(42)

    def test_branch_without_issue_number_skips_issue_fetch(
        self, tmp_path: Path
    ) -> None:
        """No issue number → no IssueManager, issue_data=None."""
        pr_manager = MagicMock()
        with (
            patch(ISSUE_MANAGER) as mock_im_cls,
            patch(DETECT, return_value="main") as mock_detect,
        ):
            result = _resolve_base_branch(tmp_path, "feature-branch", pr_manager)

        assert result == ("main", None)
        mock_im_cls.assert_not_called()
        mock_detect.assert_called_once_with(
            tmp_path,
            current_branch="feature-branch",
            issue_data=None,
            pr_manager=pr_manager,
        )

    def test_issue_manager_init_failure_falls_through(self, tmp_path: Path) -> None:
        """IssueManager construction failure → detection with issue_data=None."""
        with (
            patch(ISSUE_MANAGER, side_effect=RuntimeError("no token")),
            patch(DETECT, return_value="main") as mock_detect,
        ):
            result = _resolve_base_branch(tmp_path, BRANCH, None)

        assert result == ("main", None)
        assert mock_detect.call_args.kwargs["issue_data"] is None

    def test_identity_mismatch_logs_warning_and_falls_through(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """IssueIdentityMismatchError is logged at WARNING; detection continues."""
        with (
            patch(ISSUE_MANAGER) as mock_im_cls,
            patch(DETECT, return_value="main") as mock_detect,
            caplog.at_level(logging.WARNING, logger="mcp_workspace.server"),
        ):
            mock_im_cls.return_value.get_issue.side_effect = IssueIdentityMismatchError(
                "issue #42 was transferred"
            )
            result = _resolve_base_branch(tmp_path, BRANCH, None)

        assert result == ("main", None)
        assert mock_detect.call_args.kwargs["issue_data"] is None
        mock_im_cls.return_value.get_issue.assert_called_once_with(42)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("issue #42 was transferred" in r.getMessage() for r in warnings)

    def test_generic_fetch_failure_falls_through(self, tmp_path: Path) -> None:
        """Any other get_issue failure → detection with issue_data=None."""
        with (
            patch(ISSUE_MANAGER) as mock_im_cls,
            patch(DETECT, return_value="main") as mock_detect,
        ):
            mock_im_cls.return_value.get_issue.side_effect = RuntimeError("boom")
            result = _resolve_base_branch(tmp_path, BRANCH, None)

        assert result == ("main", None)
        assert mock_detect.call_args.kwargs["issue_data"] is None
        mock_im_cls.return_value.get_issue.assert_called_once_with(42)

    def test_empty_issue_sentinel_falls_through(self, tmp_path: Path) -> None:
        """get_issue returning number == 0 is treated as no issue."""
        with (
            patch(ISSUE_MANAGER) as mock_im_cls,
            patch(DETECT, return_value="main") as mock_detect,
        ):
            mock_im_cls.return_value.get_issue.return_value = _issue(
                number=0, base_branch_error=SENTENCE
            )
            result = _resolve_base_branch(tmp_path, BRANCH, None)

        assert result == ("main", None)
        assert mock_detect.call_args.kwargs["issue_data"] is None
        mock_im_cls.return_value.get_issue.assert_called_once_with(42)


class TestGetBaseBranch:
    """Tests for the ``get_base_branch`` MCP tool."""

    def test_malformed_returns_error_string(self) -> None:
        """A malformed Base Branch section is returned as an error string."""
        with (
            patch(PR_MANAGER),
            patch(CURRENT_BRANCH, return_value=BRANCH),
            patch(ISSUE_MANAGER) as mock_im_cls,
            patch(DETECT) as mock_detect,
        ):
            mock_im_cls.return_value.get_issue.return_value = _issue(
                base_branch_error=SENTENCE
            )
            result = get_base_branch()

        assert result == f"Error: issue #42: {SENTENCE}"
        mock_detect.assert_not_called()

    def test_valid_returns_detected_branch(self) -> None:
        """The detected base branch is returned as-is."""
        with (
            patch(PR_MANAGER),
            patch(CURRENT_BRANCH, return_value=BRANCH),
            patch(ISSUE_MANAGER) as mock_im_cls,
            patch(DETECT, return_value="develop"),
        ):
            mock_im_cls.return_value.get_issue.return_value = _issue(
                base_branch="develop"
            )
            result = get_base_branch()

        assert result == "develop"

    def test_detection_none_returns_main(self) -> None:
        """Nothing detected → "main"."""
        with (
            patch(PR_MANAGER),
            patch(CURRENT_BRANCH, return_value="feature-branch"),
            patch(DETECT, return_value=None),
        ):
            result = get_base_branch()

        assert result == "main"

    def test_no_current_branch_returns_main(self) -> None:
        """Detached HEAD → "main" without detection."""
        with (
            patch(PR_MANAGER),
            patch(CURRENT_BRANCH, return_value=None),
            patch(DETECT) as mock_detect,
        ):
            result = get_base_branch()

        assert result == "main"
        mock_detect.assert_not_called()
