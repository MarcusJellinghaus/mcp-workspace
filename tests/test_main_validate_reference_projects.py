"""Tests for main.validate_reference_projects."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.main import _check_reference_projects, validate_reference_projects
from mcp_workspace.reference_projects import ReferenceProject


class TestValidateReferenceProjects:
    """Test reference project argument validation."""

    @patch("mcp_workspace.main.detect_and_verify_url", return_value=None)
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_auto_rename_duplicates(
        self,
        mock_is_dir: MagicMock,
        mock_exists: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Test auto-renaming duplicate project names."""
        # Mock path validation
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        # Test duplicate names get auto-renamed
        reference_args = [
            "name=proj,path=/path/to/proj1",
            "name=proj,path=/path/to/proj2",
            "name=proj,path=/path/to/proj3",
        ]
        result = validate_reference_projects(
            reference_args, project_dir=Path("/unrelated/project")
        )

        assert "proj" in result
        assert "proj_2" in result
        assert "proj_3" in result
        assert isinstance(result["proj"], ReferenceProject)
        assert result["proj"].path == Path("/path/to/proj1").resolve()
        assert result["proj_2"].path == Path("/path/to/proj2").resolve()
        assert result["proj_3"].path == Path("/path/to/proj3").resolve()

    @patch("mcp_workspace.main.stdlogger")
    def test_invalid_format_warnings(self, mock_logger: MagicMock) -> None:
        """Test warnings for invalid argument formats."""
        # Test missing 'name' key
        reference_args = ["path=/path/to/proj"]
        result = validate_reference_projects(
            reference_args, project_dir=Path("/unrelated/project")
        )
        assert result == {}
        calls = mock_logger.warning.call_args_list
        found_missing_name = any("missing 'name' key" in str(call) for call in calls)
        assert found_missing_name

        mock_logger.reset_mock()

        # Test missing 'path' key
        reference_args = ["name=proj"]
        result = validate_reference_projects(
            reference_args, project_dir=Path("/unrelated/project")
        )
        assert result == {}
        calls = mock_logger.warning.call_args_list
        found_missing_path = any("missing 'path' key" in str(call) for call in calls)
        assert found_missing_path

    @patch("mcp_workspace.main.detect_and_verify_url", return_value=None)
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_path_normalization(
        self,
        mock_is_dir: MagicMock,
        mock_exists: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Test conversion to canonical resolved paths."""
        # Mock path validation
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        # Test relative path gets converted to canonical resolved path
        reference_args = ["name=proj,path=./relative/path"]
        result = validate_reference_projects(
            reference_args, project_dir=Path("/unrelated/project")
        )

        # Should contain canonical resolved path
        assert "proj" in result
        assert isinstance(result["proj"], ReferenceProject)
        assert result["proj"].path == Path("./relative/path").resolve()

    @pytest.mark.parametrize(
        "ref_subpath, project_subpath, expected_count, expected_warning_fragment",
        [
            ("main", "main", 0, "same directory"),
            ("main/sub", "main", 0, "subdirectory of the main project"),
            ("projects", "projects/main", 0, "parent of the main project"),
            ("other", "main", 1, None),
        ],
    )
    def test_overlap_detection(
        self,
        tmp_path: Path,
        ref_subpath: str,
        project_subpath: str,
        expected_count: int,
        expected_warning_fragment: str | None,
    ) -> None:
        """Test that reference projects overlapping with project_dir are filtered out."""
        # Create real directory structure
        ref_dir = tmp_path / ref_subpath
        ref_dir.mkdir(parents=True, exist_ok=True)
        project_dir = tmp_path / project_subpath
        project_dir.mkdir(parents=True, exist_ok=True)

        reference_args = [f"name=ref,path={ref_dir}"]

        with patch("mcp_workspace.main.stdlogger") as mock_logger:
            with patch("mcp_workspace.main.detect_and_verify_url", return_value=None):
                result = validate_reference_projects(
                    reference_args, project_dir=project_dir
                )

                assert len(result) == expected_count
                if expected_warning_fragment:
                    assert any(
                        expected_warning_fragment in str(call)
                        for call in mock_logger.warning.call_args_list
                    )
                else:
                    mock_logger.warning.assert_not_called()
                    assert "ref" in result
                    assert isinstance(result["ref"], ReferenceProject)
                    assert result["ref"].path == ref_dir.resolve()

    @patch("mcp_workspace.main.stdlogger")
    @patch("mcp_workspace.main.Path.exists")
    def test_nonexistent_path_warning(
        self, mock_exists: MagicMock, mock_logger: MagicMock
    ) -> None:
        """Test warnings for non-existent paths without URL."""
        mock_exists.return_value = False

        reference_args = ["name=proj,path=/nonexistent/path"]
        result = validate_reference_projects(
            reference_args, project_dir=Path("/unrelated/project")
        )

        # Should log warning and return empty dict
        mock_logger.warning.assert_called()
        assert result == {}

    @patch("mcp_workspace.main.detect_and_verify_url")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_url_resolved_from_detect_and_verify(
        self,
        mock_is_dir: MagicMock,
        mock_exists: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Test URL from detect_and_verify_url is stored in ReferenceProject."""
        mock_exists.return_value = True
        mock_is_dir.return_value = True
        mock_detect.return_value = "https://github.com/org/repo"

        reference_args = ["name=proj,path=/path/to/proj"]
        result = validate_reference_projects(
            reference_args, project_dir=Path("/unrelated/project")
        )

        assert "proj" in result
        assert result["proj"].url == "https://github.com/org/repo"

    @patch("mcp_workspace.main.detect_and_verify_url")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_url_mismatch_fatal(
        self,
        mock_is_dir: MagicMock,
        mock_exists: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Test detect_and_verify_url raising ValueError propagates."""
        mock_exists.return_value = True
        mock_is_dir.return_value = True
        mock_detect.side_effect = ValueError("URL mismatch for 'proj'")

        reference_args = ["name=proj,path=/path/to/proj,url=https://wrong.com/repo"]
        with pytest.raises(ValueError, match="URL mismatch"):
            validate_reference_projects(
                reference_args, project_dir=Path("/unrelated/project")
            )

    @patch("mcp_workspace.main.detect_and_verify_url")
    @patch("mcp_workspace.main.Path.exists")
    def test_path_missing_with_url_allowed(
        self,
        mock_exists: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Test path doesn't exist but URL set — accepted."""
        mock_exists.return_value = False
        mock_detect.return_value = "https://github.com/org/repo"

        reference_args = [
            "name=proj,path=/nonexistent/path,url=https://github.com/org/repo"
        ]
        result = validate_reference_projects(
            reference_args, project_dir=Path("/unrelated/project")
        )

        assert "proj" in result
        assert isinstance(result["proj"], ReferenceProject)
        assert result["proj"].url == "https://github.com/org/repo"

    @patch("mcp_workspace.main.stdlogger")
    @patch("mcp_workspace.main.Path.exists")
    def test_path_missing_without_url_skipped(
        self,
        mock_exists: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        """Test path doesn't exist, no URL — warning + skip."""
        mock_exists.return_value = False

        reference_args = ["name=proj,path=/nonexistent/path"]
        result = validate_reference_projects(
            reference_args, project_dir=Path("/unrelated/project")
        )

        assert result == {}
        mock_logger.warning.assert_called()

    @patch("mcp_workspace.main.detect_and_verify_url", return_value=None)
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_empty_name_validation(
        self,
        mock_is_dir: MagicMock,
        mock_exists: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Test validation of empty project names."""
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        # Test empty name gets rejected (name key missing entirely)
        reference_args = ["path=/path/to/proj"]
        with patch("mcp_workspace.main.stdlogger") as mock_logger:
            result = validate_reference_projects(
                reference_args, project_dir=Path("/unrelated/project")
            )

            # Should log warning for missing name
            mock_logger.warning.assert_called()
            assert result == {}


_UNRELATED = Path("/unrelated/project")


class TestCheckReferenceProjects:
    """Test the (valid, rejected) split returned by _check_reference_projects."""

    def test_empty_input(self) -> None:
        """No arguments → nothing valid, nothing rejected."""
        assert _check_reference_projects([], _UNRELATED) == ({}, [])

    @pytest.mark.parametrize(
        "arg, label, reason",
        [
            ("proj=/path/to/dir", "proj=/path/to/dir", "old format"),
            ("path=/path/to/proj", "path=/path/to/proj", "missing name"),
            ("name=proj", "proj", "missing path"),
        ],
    )
    def test_format_rejections(self, arg: str, label: str, reason: str) -> None:
        """Malformed arguments are rejected with the raw argument as label."""
        valid, rejected = _check_reference_projects([arg], _UNRELATED)
        assert valid == {}
        assert rejected == [(label, reason)]

    @patch("mcp_workspace.main.Path.exists", return_value=False)
    def test_path_not_found(self, _mock_exists: MagicMock) -> None:
        """A missing path without url is rejected under the project name."""
        valid, rejected = _check_reference_projects(
            ["name=proj,path=/nonexistent/path"], _UNRELATED
        )
        assert valid == {}
        assert rejected == [("proj", "path not found")]

    @patch("mcp_workspace.main.Path.is_dir", return_value=False)
    @patch("mcp_workspace.main.Path.exists", return_value=True)
    def test_not_a_directory(
        self, _mock_exists: MagicMock, _mock_is_dir: MagicMock
    ) -> None:
        """A path that is a file is rejected under the project name."""
        valid, rejected = _check_reference_projects(
            ["name=proj,path=/path/to/file.txt"], _UNRELATED
        )
        assert valid == {}
        assert rejected == [("proj", "not a directory")]

    @pytest.mark.parametrize(
        "ref_subpath, project_subpath, reason",
        [
            ("main", "main", "same directory as workspace"),
            ("main/sub", "main", "inside workspace"),
            ("projects", "projects/main", "parent of workspace"),
        ],
    )
    def test_overlap_rejections(
        self, tmp_path: Path, ref_subpath: str, project_subpath: str, reason: str
    ) -> None:
        """References overlapping the workspace are rejected with a fixed reason."""
        ref_dir = tmp_path / ref_subpath
        ref_dir.mkdir(parents=True, exist_ok=True)
        project_dir = tmp_path / project_subpath
        project_dir.mkdir(parents=True, exist_ok=True)

        valid, rejected = _check_reference_projects(
            [f"name=ref,path={ref_dir}"], project_dir
        )
        assert valid == {}
        assert rejected == [("ref", reason)]

    @patch("mcp_workspace.main.detect_and_verify_url", return_value=None)
    @patch("mcp_workspace.main.Path.exists", return_value=True)
    @patch("mcp_workspace.main.Path.is_dir", return_value=True)
    def test_duplicates_accepted_not_rejected(
        self,
        _mock_is_dir: MagicMock,
        _mock_exists: MagicMock,
        _mock_detect: MagicMock,
    ) -> None:
        """Duplicate names are auto-renamed into valid, never rejected."""
        valid, rejected = _check_reference_projects(
            ["name=proj,path=/path/to/proj1", "name=proj,path=/path/to/proj2"],
            _UNRELATED,
        )
        assert list(valid) == ["proj", "proj_2"]
        assert rejected == []

    @patch("mcp_workspace.main.detect_and_verify_url", return_value=None)
    @patch("mcp_workspace.main.Path.exists", return_value=True)
    @patch("mcp_workspace.main.Path.is_dir", return_value=True)
    def test_validate_reference_projects_returns_only_valid(
        self,
        _mock_is_dir: MagicMock,
        _mock_exists: MagicMock,
        _mock_detect: MagicMock,
    ) -> None:
        """The public wrapper returns the valid dict and drops rejected entries."""
        result = validate_reference_projects(
            ["name=proj,path=/path/to/proj", "name=broken"], _UNRELATED
        )
        assert isinstance(result, dict)
        assert list(result) == ["proj"]

    @patch("mcp_workspace.main.stdlogger")
    def test_credentials_scrubbed_in_label_and_warning(
        self, mock_logger: MagicMock
    ) -> None:
        """A token in a rejected argument appears neither in the label nor the log."""
        arg = "path=/x,url=https://user:tok@github.com/o/r"
        valid, rejected = _check_reference_projects([arg], _UNRELATED)

        assert valid == {}
        assert rejected == [("path=/x,url=https://github.com/o/r", "missing name")]
        mock_logger.warning.assert_called_once()
        assert "tok" not in str(mock_logger.warning.call_args)
