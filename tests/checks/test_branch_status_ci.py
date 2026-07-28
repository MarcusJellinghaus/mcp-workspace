"""Tests for branch_status._collect_ci_status."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.checks.branch_status import CIStatus, _collect_ci_status


class TestCollectCIStatus:
    """Tests for _collect_ci_status."""

    @pytest.fixture(autouse=True)
    def _github_token(self) -> Iterator[None]:
        """Provide a token so the missing-token gate does not short-circuit."""
        with patch(
            "mcp_workspace.checks.branch_status.get_github_token",
            return_value="tok",
        ):
            yield

    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    def test_passed(self, mock_ci_cls: MagicMock) -> None:
        mock_ci = MagicMock()
        mock_ci.get_latest_ci_status.return_value = {
            "run": {"conclusion": "success", "status": "completed"},
            "jobs": [],
        }
        mock_ci_cls.return_value = mock_ci
        status, details, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.PASSED
        assert details is None
        assert failing_names == []

    @patch("mcp_workspace.checks.branch_status.build_ci_error_details")
    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    def test_failed(self, mock_ci_cls: MagicMock, mock_build: MagicMock) -> None:
        mock_ci = MagicMock()
        mock_ci.get_latest_ci_status.return_value = {
            "run": {"conclusion": "failure", "status": "completed"},
            "jobs": [],
        }
        mock_ci_cls.return_value = mock_ci
        mock_build.return_value = "error details"
        status, details, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.FAILED
        assert details == "error details"
        assert failing_names == []

    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    def test_pending(self, mock_ci_cls: MagicMock) -> None:
        mock_ci = MagicMock()
        mock_ci.get_latest_ci_status.return_value = {
            "run": {"conclusion": None, "status": "in_progress"},
            "jobs": [],
        }
        mock_ci_cls.return_value = mock_ci
        status, details, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.PENDING
        assert failing_names == []

    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    def test_not_configured(self, mock_ci_cls: MagicMock) -> None:
        mock_ci = MagicMock()
        mock_ci.get_latest_ci_status.return_value = {"run": {}, "jobs": []}
        mock_ci_cls.return_value = mock_ci
        status, _, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.NOT_CONFIGURED
        assert failing_names == []

    @patch("mcp_workspace.checks.branch_status.build_ci_error_details")
    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    def test_failed_with_details_exception(
        self, mock_ci_cls: MagicMock, mock_build: MagicMock
    ) -> None:
        """build_ci_error_details raising still returns FAILED, not NOT_CONFIGURED."""
        mock_ci = MagicMock()
        mock_ci.get_latest_ci_status.return_value = {
            "run": {"conclusion": "failure", "status": "completed"},
            "jobs": [],
        }
        mock_ci_cls.return_value = mock_ci
        mock_build.side_effect = Exception("log fetch failed")
        status, details, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.FAILED
        assert details is None
        assert failing_names == []

    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    def test_pending_via_status_fallback(self, mock_ci_cls: MagicMock) -> None:
        """conclusion=None, status='in_progress' should return PENDING."""
        mock_ci = MagicMock()
        mock_ci.get_latest_ci_status.return_value = {
            "run": {"conclusion": None, "status": "in_progress"},
            "jobs": [],
        }
        mock_ci_cls.return_value = mock_ci
        status, details, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.PENDING
        assert details is None
        assert failing_names == []

    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    def test_exception_returns_not_configured(self, mock_ci_cls: MagicMock) -> None:
        mock_ci_cls.side_effect = Exception("fail")
        status, _, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.NOT_CONFIGURED
        assert failing_names == []

    @patch("mcp_workspace.checks.branch_status.build_ci_error_details")
    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    def test_workflow_success_with_failed_job_returns_failed(
        self, mock_ci_cls: MagicMock, mock_build: MagicMock
    ) -> None:
        """workflow=success but a job has conclusion=failure → FAILED + names."""
        mock_ci = MagicMock()
        mock_ci.get_latest_ci_status.return_value = {
            "run": {"conclusion": "success", "status": "completed"},
            "jobs": [{"name": "mssql-integration", "conclusion": "failure"}],
        }
        mock_ci_cls.return_value = mock_ci
        mock_build.return_value = "error details"
        status, details, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.FAILED
        assert details == "error details"
        assert failing_names == ["mssql-integration"]

    @patch("mcp_workspace.checks.branch_status.build_ci_error_details")
    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    def test_workflow_success_with_cancelled_job_returns_failed(
        self, mock_ci_cls: MagicMock, mock_build: MagicMock
    ) -> None:
        """workflow=success but a job has conclusion=cancelled → FAILED + names."""
        mock_ci = MagicMock()
        mock_ci.get_latest_ci_status.return_value = {
            "run": {"conclusion": "success", "status": "completed"},
            "jobs": [{"name": "lint", "conclusion": "cancelled"}],
        }
        mock_ci_cls.return_value = mock_ci
        mock_build.return_value = "details"
        status, _details, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.FAILED
        assert failing_names == ["lint"]

    @patch("mcp_workspace.checks.branch_status.build_ci_error_details")
    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    def test_workflow_success_with_timed_out_job_returns_failed(
        self, mock_ci_cls: MagicMock, mock_build: MagicMock
    ) -> None:
        """workflow=success but a job has conclusion=timed_out → FAILED + names."""
        mock_ci = MagicMock()
        mock_ci.get_latest_ci_status.return_value = {
            "run": {"conclusion": "success", "status": "completed"},
            "jobs": [{"name": "tests", "conclusion": "timed_out"}],
        }
        mock_ci_cls.return_value = mock_ci
        mock_build.return_value = "details"
        status, _details, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.FAILED
        assert failing_names == ["tests"]

    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    def test_workflow_success_clean_returns_passed_with_empty_names(
        self, mock_ci_cls: MagicMock
    ) -> None:
        """workflow=success and no failing jobs → PASSED with empty list."""
        mock_ci = MagicMock()
        mock_ci.get_latest_ci_status.return_value = {
            "run": {"conclusion": "success", "status": "completed"},
            "jobs": [{"name": "tests", "conclusion": "success"}],
        }
        mock_ci_cls.return_value = mock_ci
        status, details, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.PASSED
        assert details is None
        assert failing_names == []

    @patch("mcp_workspace.checks.branch_status.CIResultsManager")
    def test_workflow_success_with_jobs_fetch_warning_returns_pending(
        self, mock_ci_cls: MagicMock
    ) -> None:
        """workflow=success with jobs_fetch_warning → PENDING."""
        mock_ci = MagicMock()
        mock_ci.get_latest_ci_status.return_value = {
            "run": {
                "conclusion": "success",
                "status": "completed",
                "jobs_fetch_warning": "rate limited",
            },
            "jobs": [],
        }
        mock_ci_cls.return_value = mock_ci
        status, details, failing_names = _collect_ci_status(Path("/tmp"), "main", 300)
        assert status == CIStatus.PENDING
        assert details is None
        assert failing_names == []
