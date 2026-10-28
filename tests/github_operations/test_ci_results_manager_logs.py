"""Tests for CIResultsManager log retrieval methods."""

import io
import zipfile
from pathlib import Path
from typing import Dict
from unittest.mock import Mock, patch

import pytest
import requests
from github import GithubException

from mcp_workspace.github_operations import CIResultsManager, CIStatusData


class TestDownloadAndExtractZip:
    """Test the _download_and_extract_zip helper method."""

    @pytest.fixture
    def ci_manager(self) -> CIResultsManager:
        """CIResultsManager instance for testing."""
        repo_url = "https://github.com/test/repo.git"

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="test_token",
        ):
            with patch("github.Github"):
                return CIResultsManager(repo_url=repo_url)

    @patch("requests.get")
    def test_successful_download(
        self, mock_requests: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test successful ZIP download and extraction."""
        # Create a mock ZIP file with test content
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            zip_file.writestr("test/1_Setup.txt", "Setting up test environment...")
            zip_file.writestr(
                "test/2_Run tests.txt", "Running tests...\nTest failed: assertion error"
            )
            zip_file.writestr("build/1_Setup.txt", "Setting up build environment...")

        zip_buffer.seek(0)

        # Mock HTTP response
        mock_response = Mock()
        mock_response.content = zip_buffer.getvalue()
        mock_response.raise_for_status = Mock()
        mock_response.history = []
        mock_requests.return_value = mock_response

        # Test the method
        result = ci_manager._download_and_extract_zip(
            "https://api.github.com/repos/test/repo/actions/runs/123/logs"
        )

        # Verify the result
        expected = {
            "test/1_Setup.txt": "Setting up test environment...",
            "test/2_Run tests.txt": "Running tests...\nTest failed: assertion error",
            "build/1_Setup.txt": "Setting up build environment...",
        }
        assert result == expected

        # Verify HTTP request was made correctly
        mock_requests.assert_called_once_with(
            "https://api.github.com/repos/test/repo/actions/runs/123/logs",
            headers={
                "Authorization": "Bearer test_token",
                "Accept": "application/vnd.github.v3+json",
            },
            allow_redirects=True,
            timeout=(10, 60),
        )
        mock_response.raise_for_status.assert_called_once()

    @patch("requests.get")
    def test_http_error(
        self, mock_requests: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test handling of HTTP errors during download."""
        # Mock HTTP error
        mock_requests.side_effect = requests.exceptions.RequestException(
            "Network error"
        )

        # Test the method - should return empty dict on error
        result = ci_manager._download_and_extract_zip(
            "https://api.github.com/repos/test/repo/actions/runs/123/logs"
        )

        assert result == {}

        mock_requests.assert_called_once()

    @patch("requests.get")
    def test_invalid_zip(
        self, mock_requests: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test handling of invalid ZIP content."""
        # Mock HTTP response with invalid ZIP content
        mock_response = Mock()
        mock_response.content = b"This is not a valid ZIP file"
        mock_response.raise_for_status = Mock()
        mock_response.history = []
        mock_requests.return_value = mock_response

        # Test the method - should return empty dict on ZIP error
        result = ci_manager._download_and_extract_zip(
            "https://api.github.com/repos/test/repo/actions/runs/123/logs"
        )

        assert result == {}

        mock_requests.assert_called_once()
        mock_response.raise_for_status.assert_called_once()


class TestDownloadTrafficLog:
    """Test traffic-log lines written by _download_and_extract_zip."""

    URL = "https://api.github.com/repos/test/repo/actions/runs/123/logs"

    @pytest.fixture
    def ci_manager(self) -> CIResultsManager:
        """CIResultsManager instance for testing."""
        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="test_token",
        ):
            with patch("github.Github"):
                return CIResultsManager(repo_url="https://github.com/test/repo.git")

    @pytest.fixture
    def log_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Turn the traffic log on, writing into ``tmp_path``."""
        monkeypatch.setattr(
            "mcp_workspace.config.get_traffic_log_dir", lambda: tmp_path
        )
        return tmp_path

    @staticmethod
    def _lines(directory: Path) -> list[str]:
        files = list(directory.glob("github_requests_*.log"))
        assert len(files) == 1
        return files[0].read_text(encoding="utf-8").splitlines()

    @patch("mcp_workspace.github_operations.ci_results_manager.requests.get")
    def test_success_uses_first_hop_rate_limit(
        self, mock_get: Mock, ci_manager: CIResultsManager, log_dir: Path
    ) -> None:
        """A redirected download logs the final status with the API hop's headers."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            zip_file.writestr("result.txt", "ok")
        redirect = Mock()
        redirect.headers = {
            "X-RateLimit-Resource": "core",
            "X-RateLimit-Remaining": "4100",
        }
        mock_response = Mock()
        mock_response.content = zip_buffer.getvalue()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.history = [redirect]
        mock_get.return_value = mock_response

        result = ci_manager._download_and_extract_zip(self.URL)

        assert result == {"result.txt": "ok"}
        lines = self._lines(log_dir)
        assert len(lines) == 1
        assert "GET /repos/test/repo/actions/runs/123/logs | 200 | core 4100" in (
            lines[0]
        )
        assert "CIResultsManager._download_and_extract_zip" in lines[0]

    @patch("mcp_workspace.github_operations.ci_results_manager.requests.get")
    def test_request_exception_logs_err_line(
        self, mock_get: Mock, ci_manager: CIResultsManager, log_dir: Path
    ) -> None:
        """A raising requests.get logs one ERR line and still returns {}."""
        mock_get.side_effect = requests.exceptions.ReadTimeout("slow")

        result = ci_manager._download_and_extract_zip(self.URL)

        assert result == {}
        lines = self._lines(log_dir)
        assert len(lines) == 1
        assert " | ERR ReadTimeout | " in lines[0]

    @patch("mcp_workspace.github_operations.ci_results_manager.requests.get")
    def test_http_404_logs_status(
        self, mock_get: Mock, ci_manager: CIResultsManager, log_dir: Path
    ) -> None:
        """A 404 response logs one line with status 404 and returns {}."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.headers = {}
        mock_response.history = []
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "404 Not Found"
        )
        mock_get.return_value = mock_response

        result = ci_manager._download_and_extract_zip(self.URL)

        assert result == {}
        lines = self._lines(log_dir)
        assert len(lines) == 1
        assert "GET /repos/test/repo/actions/runs/123/logs | 404 | - - | " in lines[0]

    @patch("mcp_workspace.github_operations.ci_results_manager.requests.get")
    def test_log_off_writes_no_file(
        self, mock_get: Mock, ci_manager: CIResultsManager, tmp_path: Path
    ) -> None:
        """With the log off (fixture default) no file is written."""
        mock_get.side_effect = requests.exceptions.ReadTimeout("slow")

        assert ci_manager._download_and_extract_zip(self.URL) == {}
        assert not list(tmp_path.glob("github_requests_*.log"))


class TestGetRunLogs:
    """Test the get_run_logs method."""

    @patch("mcp_workspace.github_operations.ci_results_manager.requests.get")
    def test_successful_logs_retrieval(
        self, mock_requests: Mock, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test successful retrieval of workflow run logs."""
        # Mock workflow run
        mock_run = Mock()
        mock_run.id = 123456789
        mock_run.logs_url = (
            "https://api.github.com/repos/test/repo/actions/runs/123456789/logs"
        )
        mock_repo.get_workflow_run.return_value = mock_run

        # Create a mock ZIP file with log content
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            zip_file.writestr("test/1_Setup.txt", "Setting up test environment...\n")
            zip_file.writestr(
                "test/2_Run tests.txt", "Running tests...\nTest failed: assertion error"
            )
            zip_file.writestr("build/1_Setup.txt", "Setting up build environment...")

        zip_buffer.seek(0)

        # Mock HTTP response
        mock_response = Mock()
        mock_response.content = zip_buffer.getvalue()
        mock_response.raise_for_status = Mock()
        mock_response.history = []
        mock_requests.return_value = mock_response

        # Test the method
        result = ci_manager.get_run_logs(123456789)

        # Verify the result contains all logs
        expected = {
            "test/1_Setup.txt": "Setting up test environment...\n",
            "test/2_Run tests.txt": "Running tests...\nTest failed: assertion error",
            "build/1_Setup.txt": "Setting up build environment...",
        }
        assert result == expected

        # Verify API calls
        mock_repo.get_workflow_run.assert_called_once_with(123456789)

    def test_invalid_run_id(self, ci_manager: CIResultsManager) -> None:
        """Test with invalid run ID raises ValueError."""
        # Test negative run ID - raises ValueError
        with pytest.raises(ValueError, match="Invalid workflow run ID: -1"):
            ci_manager.get_run_logs(-1)

        # Test zero run ID - raises ValueError
        with pytest.raises(ValueError, match="Invalid workflow run ID: 0"):
            ci_manager.get_run_logs(0)
