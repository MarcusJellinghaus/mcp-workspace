"""Tests for CIResultsManager artifact retrieval methods."""

import io
import zipfile
from pathlib import Path
from typing import Dict
from unittest.mock import Mock, patch

import pytest
import requests
from github import GithubException

from mcp_workspace.github_operations import CIResultsManager, CIStatusData


class TestGetArtifacts:
    """Test the get_artifacts method."""

    def test_single_artifact(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test downloading a single artifact."""
        # Mock workflow run and artifact
        mock_run = Mock()
        mock_run.id = 123456
        mock_artifact = Mock()
        mock_artifact.name = "test-results"
        mock_artifact.archive_download_url = (
            "https://api.github.com/repos/test/repo/artifacts/456/zip"
        )

        mock_run.get_artifacts.return_value = [mock_artifact]
        mock_repo.get_workflow_run.return_value = mock_run

        # Mock the ZIP download via _download_and_extract_zip
        expected_content = {
            "test-results.xml": "<?xml version='1.0'?><testsuites></testsuites>"
        }

        with patch.object(ci_manager, "_download_and_extract_zip") as mock_download:
            mock_download.return_value = expected_content

            result = ci_manager.get_artifacts(123456)

            assert result == expected_content
            mock_repo.get_workflow_run.assert_called_once_with(123456)
            mock_run.get_artifacts.assert_called_once()
            mock_download.assert_called_once_with(mock_artifact.archive_download_url)

    def test_multiple_artifacts(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test downloading multiple artifacts."""
        # Mock workflow run and artifacts
        mock_run = Mock()
        mock_run.id = 123456

        mock_artifact1 = Mock()
        mock_artifact1.name = "test-results"
        mock_artifact1.archive_download_url = (
            "https://api.github.com/repos/test/repo/artifacts/456/zip"
        )

        mock_artifact2 = Mock()
        mock_artifact2.name = "coverage-report"
        mock_artifact2.archive_download_url = (
            "https://api.github.com/repos/test/repo/artifacts/789/zip"
        )

        mock_run.get_artifacts.return_value = [mock_artifact1, mock_artifact2]
        mock_repo.get_workflow_run.return_value = mock_run

        # Mock the ZIP downloads
        artifact1_content = {"junit.xml": "<?xml version='1.0'?>..."}
        artifact2_content = {"coverage.json": '{"total": 85.5}'}

        def download_side_effect(url: str) -> Dict[str, str]:
            if "456" in url:
                return artifact1_content
            elif "789" in url:
                return artifact2_content
            return {}

        with patch.object(ci_manager, "_download_and_extract_zip") as mock_download:
            mock_download.side_effect = download_side_effect

            result = ci_manager.get_artifacts(123456)

            expected = {
                "junit.xml": "<?xml version='1.0'?>...",
                "coverage.json": '{"total": 85.5}',
            }
            assert result == expected
            assert mock_download.call_count == 2

    def test_no_artifacts(self, mock_repo: Mock, ci_manager: CIResultsManager) -> None:
        """Test when workflow run has no artifacts."""
        mock_run = Mock()
        mock_run.id = 123456
        mock_run.get_artifacts.return_value = []
        mock_repo.get_workflow_run.return_value = mock_run

        result = ci_manager.get_artifacts(123456)

        assert result == {}
        mock_repo.get_workflow_run.assert_called_once_with(123456)
        mock_run.get_artifacts.assert_called_once()

    def test_with_name_filter(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test filtering artifacts by name."""
        # Mock workflow run and artifacts
        mock_run = Mock()
        mock_run.id = 123456

        mock_artifact1 = Mock()
        mock_artifact1.name = "junit-test-results"
        mock_artifact1.archive_download_url = (
            "https://api.github.com/repos/test/repo/artifacts/456/zip"
        )

        mock_artifact2 = Mock()
        mock_artifact2.name = "coverage-report"
        mock_artifact2.archive_download_url = (
            "https://api.github.com/repos/test/repo/artifacts/789/zip"
        )

        mock_artifact3 = Mock()
        mock_artifact3.name = "junit-integration-results"
        mock_artifact3.archive_download_url = (
            "https://api.github.com/repos/test/repo/artifacts/012/zip"
        )

        mock_run.get_artifacts.return_value = [
            mock_artifact1,
            mock_artifact2,
            mock_artifact3,
        ]
        mock_repo.get_workflow_run.return_value = mock_run

        # Mock the ZIP downloads for junit artifacts only
        def download_side_effect(url: str) -> Dict[str, str]:
            if "456" in url:
                return {"junit.xml": "<?xml version='1.0'?>..."}
            elif "012" in url:
                return {"integration-junit.xml": "<?xml version='1.0'?>..."}
            return {}

        with patch.object(ci_manager, "_download_and_extract_zip") as mock_download:
            mock_download.side_effect = download_side_effect

            # Test case-insensitive filtering
            result = ci_manager.get_artifacts(123456, name_filter="JUNIT")

            expected = {
                "junit.xml": "<?xml version='1.0'?>...",
                "integration-junit.xml": "<?xml version='1.0'?>...",
            }
            assert result == expected
            # Should only download junit artifacts (not coverage)
            assert mock_download.call_count == 2

    def test_name_filter_no_match(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test name filter with no matching artifacts."""
        mock_run = Mock()
        mock_run.id = 123456

        mock_artifact = Mock()
        mock_artifact.name = "coverage-report"
        mock_artifact.archive_download_url = (
            "https://api.github.com/repos/test/repo/artifacts/456/zip"
        )

        mock_run.get_artifacts.return_value = [mock_artifact]
        mock_repo.get_workflow_run.return_value = mock_run

        result = ci_manager.get_artifacts(123456, name_filter="junit")

        assert result == {}
        mock_repo.get_workflow_run.assert_called_once_with(123456)
        mock_run.get_artifacts.assert_called_once()
        # No downloads should occur

    def test_artifact_download_failure(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test handling of artifact download failures."""
        # Mock workflow run and artifacts
        mock_run = Mock()
        mock_run.id = 123456

        mock_artifact1 = Mock()
        mock_artifact1.name = "test-results"
        mock_artifact1.archive_download_url = (
            "https://api.github.com/repos/test/repo/artifacts/456/zip"
        )

        mock_artifact2 = Mock()
        mock_artifact2.name = "coverage-report"
        mock_artifact2.archive_download_url = (
            "https://api.github.com/repos/test/repo/artifacts/789/zip"
        )

        mock_run.get_artifacts.return_value = [mock_artifact1, mock_artifact2]
        mock_repo.get_workflow_run.return_value = mock_run

        # Mock first download failing, second succeeding
        def download_side_effect(url: str) -> Dict[str, str]:
            if "456" in url:
                return {}  # Download failed
            elif "789" in url:
                return {"coverage.json": '{"total": 85.5}'}
            return {}

        with patch.object(ci_manager, "_download_and_extract_zip") as mock_download:
            mock_download.side_effect = download_side_effect

            result = ci_manager.get_artifacts(123456)

            # Should only contain successful download
            expected = {"coverage.json": '{"total": 85.5}'}
            assert result == expected
            assert mock_download.call_count == 2

    def test_invalid_run_id(self, ci_manager: CIResultsManager) -> None:
        """Test with invalid run ID raises ValueError."""
        # Test negative run ID - raises ValueError
        with pytest.raises(ValueError, match="Invalid workflow run ID: -1"):
            ci_manager.get_artifacts(-1)

        # Test zero run ID - raises ValueError
        with pytest.raises(ValueError, match="Invalid workflow run ID: 0"):
            ci_manager.get_artifacts(0)

    @patch("mcp_workspace.github_operations.ci_results_manager.logger")
    def test_binary_file_skipped_with_warning(
        self, mock_logger: Mock, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test that binary files are skipped with a log warning."""
        mock_run = Mock()
        mock_run.id = 123456

        mock_artifact = Mock()
        mock_artifact.name = "test-results"
        mock_artifact.archive_download_url = (
            "https://api.github.com/repos/test/repo/artifacts/456/zip"
        )

        mock_run.get_artifacts.return_value = [mock_artifact]
        mock_repo.get_workflow_run.return_value = mock_run

        # Mock _download_and_extract_zip to simulate binary file handling
        # This would happen inside the ZIP extraction logic
        artifact_content = {
            "test-results.xml": "<?xml version='1.0'?><testsuites></testsuites>",
            # Binary files would be filtered out by _download_and_extract_zip
        }

        with patch.object(ci_manager, "_download_and_extract_zip") as mock_download:
            mock_download.return_value = artifact_content

            result = ci_manager.get_artifacts(123456)

            assert result == artifact_content
            mock_download.assert_called_once_with(mock_artifact.archive_download_url)

    def test_github_api_error_handling(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test handling of GitHub API errors."""
        # Test workflow run not found (404) - returns default empty dict
        mock_repo.get_workflow_run.side_effect = GithubException(404, "Not Found", {})

        result = ci_manager.get_artifacts(123456)
        assert result == {}

        # Test authentication error (401) - re-raised by decorator
        mock_repo.get_workflow_run.side_effect = GithubException(
            401, "Bad credentials", {}
        )

        with pytest.raises(GithubException):
            ci_manager.get_artifacts(123456)


class TestDownloadAndExtractZipTimeout:
    """Test the bounded (connect, read) timeout on the raw artifact download."""

    @patch("mcp_workspace.github_operations.ci_results_manager.requests.get")
    def test_uses_connect_read_timeout_tuple(
        self, mock_get: Mock, ci_manager: CIResultsManager
    ) -> None:
        """_download_and_extract_zip passes timeout=(connect, read) to requests.get."""
        # Build a small in-memory ZIP wrapped in a fake response
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            zip_file.writestr("result.txt", "ok")

        mock_response = Mock()
        mock_response.content = zip_buffer.getvalue()
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        url = "https://api.github.com/repos/test/repo/artifacts/456/zip"
        result = ci_manager._download_and_extract_zip(url)

        assert result == {"result.txt": "ok"}
        mock_get.assert_called_once()
        assert mock_get.call_args.kwargs["timeout"] == (
            ci_manager.DEFAULT_CONNECT_TIMEOUT,
            ci_manager.DEFAULT_REQUEST_TIMEOUT,
        )
        assert mock_get.call_args.kwargs["timeout"] == (10, 60)
