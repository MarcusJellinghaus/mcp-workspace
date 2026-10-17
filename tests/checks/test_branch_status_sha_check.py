"""Tests for branch_status_ci._is_stale_ci_run."""

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.checks.branch_status_ci import _is_stale_ci_run

_PROJECT_DIR = Path("/tmp")
_BRANCH_NAME = "main"


class TestIsStaleCIRun:
    """Tests for _is_stale_ci_run."""

    @patch("mcp_workspace.checks.branch_status_ci.get_remote_branch_commit_sha")
    @patch("mcp_workspace.checks.branch_status_ci.get_latest_commit_sha")
    def test_stale_when_pushed_and_mismatched(
        self, mock_head: MagicMock, mock_origin: MagicMock
    ) -> None:
        mock_head.return_value = "abc"
        mock_origin.return_value = "abc"
        assert _is_stale_ci_run(_PROJECT_DIR, _BRANCH_NAME, "old") is True

    @patch("mcp_workspace.checks.branch_status_ci.get_remote_branch_commit_sha")
    @patch("mcp_workspace.checks.branch_status_ci.get_latest_commit_sha")
    def test_not_stale_when_matching(
        self, mock_head: MagicMock, mock_origin: MagicMock
    ) -> None:
        mock_head.return_value = "abc"
        mock_origin.return_value = "abc"
        assert _is_stale_ci_run(_PROJECT_DIR, _BRANCH_NAME, "abc") is False

    @patch("mcp_workspace.checks.branch_status_ci.get_remote_branch_commit_sha")
    @patch("mcp_workspace.checks.branch_status_ci.get_latest_commit_sha")
    def test_skipped_when_head_unpushed(
        self, mock_head: MagicMock, mock_origin: MagicMock
    ) -> None:
        mock_head.return_value = "abc"
        mock_origin.return_value = "def"
        assert _is_stale_ci_run(_PROJECT_DIR, _BRANCH_NAME, "old") is False
        assert _is_stale_ci_run(_PROJECT_DIR, _BRANCH_NAME, "abc") is False

    @patch("mcp_workspace.checks.branch_status_ci.get_remote_branch_commit_sha")
    @patch("mcp_workspace.checks.branch_status_ci.get_latest_commit_sha")
    def test_skipped_when_origin_sha_unresolvable(
        self, mock_head: MagicMock, mock_origin: MagicMock
    ) -> None:
        mock_head.return_value = "abc"
        mock_origin.return_value = None
        assert _is_stale_ci_run(_PROJECT_DIR, _BRANCH_NAME, "old") is False

    @patch("mcp_workspace.checks.branch_status_ci.get_remote_branch_commit_sha")
    @patch("mcp_workspace.checks.branch_status_ci.get_latest_commit_sha")
    def test_skipped_when_head_sha_unresolvable(
        self, mock_head: MagicMock, mock_origin: MagicMock
    ) -> None:
        mock_head.return_value = None
        assert _is_stale_ci_run(_PROJECT_DIR, _BRANCH_NAME, "old") is False

    @pytest.mark.parametrize("run_commit_sha", [None, ""])
    def test_skipped_when_run_commit_sha_missing(
        self, run_commit_sha: Optional[str]
    ) -> None:
        assert _is_stale_ci_run(_PROJECT_DIR, _BRANCH_NAME, run_commit_sha) is False
