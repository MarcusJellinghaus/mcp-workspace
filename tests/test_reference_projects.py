"""Tests for reference project CLI parsing, validation, and integration."""

import argparse
from pathlib import Path
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.main import parse_args, validate_reference_projects
from mcp_workspace.reference_projects import ReferenceProject


class TestReferenceProjectCLI:
    """Test CLI argument parsing and validation."""

    def test_parse_single_reference_project(self) -> None:
        """Test parsing single reference project argument."""
        with patch(
            "sys.argv",
            [
                "script.py",
                "--project-dir",
                "/tmp",
                "--reference-project",
                "name=proj1,path=/path/to/proj1",
            ],
        ):
            args = parse_args()
            assert args.reference_project == ["name=proj1,path=/path/to/proj1"]

    def test_parse_multiple_reference_projects(self) -> None:
        """Test parsing multiple reference project arguments."""
        with patch(
            "sys.argv",
            [
                "script.py",
                "--project-dir",
                "/tmp",
                "--reference-project",
                "name=proj1,path=/path/to/proj1",
                "--reference-project",
                "name=proj2,path=/path/to/proj2",
            ],
        ):
            args = parse_args()
            assert args.reference_project == [
                "name=proj1,path=/path/to/proj1",
                "name=proj2,path=/path/to/proj2",
            ]

    def test_parse_file_size_limit(self) -> None:
        """Test parsing the --file-size-limit argument."""
        with patch(
            "sys.argv",
            [
                "script.py",
                "--project-dir",
                "/tmp",
                "--file-size-limit",
                "750",
            ],
        ):
            args = parse_args()
            assert args.file_size_limit == 750

    def test_parse_file_size_limit_default(self) -> None:
        """Test --file-size-limit defaults to None when omitted."""
        with patch("sys.argv", ["script.py", "--project-dir", "/tmp"]):
            args = parse_args()
            assert args.file_size_limit is None

    def test_parse_file_size_limit_rejects_non_integer(self) -> None:
        """Test argparse rejects a non-integer --file-size-limit value."""
        with patch(
            "sys.argv",
            [
                "script.py",
                "--project-dir",
                "/tmp",
                "--file-size-limit",
                "abc",
            ],
        ):
            with pytest.raises(SystemExit):
                parse_args()

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


class TestReferenceProjectServerStorage:
    """Test server storage and initialization."""

    def test_set_reference_projects(self) -> None:
        """Test setting reference projects storage."""
        import mcp_workspace.server_reference_tools as ref_tools_module
        from mcp_workspace.server_reference_tools import set_reference_projects

        # Test setting reference projects
        test_projects = {
            "proj1": ReferenceProject(
                name="proj1", path=Path("/path/to/proj1").resolve()
            ),
            "proj2": ReferenceProject(
                name="proj2", path=Path("/path/to/proj2").resolve()
            ),
        }

        set_reference_projects(test_projects)

        # Check that the global variable was updated
        assert ref_tools_module._reference_projects == test_projects

    def test_run_server_with_reference_projects(self) -> None:
        """Test run_server accepts reference projects parameter."""
        from unittest.mock import patch

        from mcp_workspace.server import run_server

        # Test that run_server can be called with reference_projects parameter
        test_projects = {
            "proj1": ReferenceProject(
                name="proj1", path=Path("/path/to/proj1").resolve()
            ),
            "proj2": ReferenceProject(
                name="proj2", path=Path("/path/to/proj2").resolve()
            ),
        }

        # Mock the mcp.run() call to avoid actually starting the server
        with patch("mcp_workspace.server.mcp.run") as mock_run:
            with patch("mcp_workspace.server.set_reference_projects") as mock_set_ref:
                run_server(Path("/test/project"), reference_projects=test_projects)

                # Verify that set_reference_projects was called with the correct arguments
                mock_set_ref.assert_called_once_with(test_projects)
                mock_run.assert_called_once()

    def test_reference_projects_logging(self) -> None:
        """Test INFO level logging during initialization."""
        from unittest.mock import patch

        from mcp_workspace.server_reference_tools import set_reference_projects

        test_projects = {
            "proj1": ReferenceProject(
                name="proj1", path=Path("/path/to/proj1").resolve()
            ),
            "proj2": ReferenceProject(
                name="proj2", path=Path("/path/to/proj2").resolve()
            ),
        }

        # Test logging behavior
        with patch("mcp_workspace.server_reference_tools.logger") as mock_logger:
            set_reference_projects(test_projects)

            # Verify INFO level logging was called
            assert mock_logger.info.called

            # Check that project details were logged
            info_calls = mock_logger.info.call_args_list
            assert len(info_calls) >= 1

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


class TestReferenceProjectIntegration:
    """Test CLI to server integration."""

    @patch("mcp_workspace.main.detect_and_verify_url", return_value=None)
    @patch("mcp_workspace.server.run_server")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_main_with_reference_projects(
        self,
        mock_is_dir: MagicMock,
        mock_exists: MagicMock,
        mock_run_server: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Test main() passes reference projects to run_server()."""
        # Mock path validation for both project dir and reference projects
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        # Mock sys.argv to simulate CLI arguments
        test_args = [
            "script.py",
            "--project-dir",
            "/test/project",
            "--reference-project",
            "name=proj1,path=/path/to/proj1",
            "--reference-project",
            "name=proj2,path=/path/to/proj2",
        ]

        with patch("sys.argv", test_args):
            with patch("mcp_workspace.main.setup_logging"):
                from mcp_workspace.main import main

                main()

                # Verify run_server was called with correct arguments
                mock_run_server.assert_called_once()
                call_args = mock_run_server.call_args

                # Check project_dir argument (positional)
                assert call_args[0][0] == Path("/test/project").resolve()

                # Check reference_projects argument (keyword)
                ref_projects = call_args[1]["reference_projects"]
                assert "proj1" in ref_projects
                assert "proj2" in ref_projects
                assert isinstance(ref_projects["proj1"], ReferenceProject)
                assert ref_projects["proj1"].path == Path("/path/to/proj1").resolve()
                assert ref_projects["proj2"].path == Path("/path/to/proj2").resolve()

    @patch("mcp_workspace.server.run_server")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_main_without_reference_projects(
        self, mock_is_dir: MagicMock, mock_exists: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Test main() works without reference projects (backward compatibility)."""
        # Mock path validation
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        # Mock sys.argv without reference projects
        test_args = ["script.py", "--project-dir", "/test/project"]

        with patch("sys.argv", test_args):
            with patch("mcp_workspace.main.setup_logging"):
                from mcp_workspace.main import main

                main()

                # Verify run_server was called with correct arguments
                mock_run_server.assert_called_once()
                call_args = mock_run_server.call_args

                # Check project_dir argument (positional)
                assert call_args[0][0] == Path("/test/project").resolve()

                # Check reference_projects argument (keyword) - should be empty dict
                assert call_args[1]["reference_projects"] == {}

    @patch("mcp_workspace.main.detect_and_verify_url", return_value=None)
    @patch("mcp_workspace.server.run_server")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_main_with_auto_rename(
        self,
        mock_is_dir: MagicMock,
        mock_exists: MagicMock,
        mock_run_server: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Test main() handles duplicate names with auto-rename."""
        # Mock path validation
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        # Mock sys.argv with duplicate project names
        test_args = [
            "script.py",
            "--project-dir",
            "/test/project",
            "--reference-project",
            "name=proj,path=/path/to/proj1",
            "--reference-project",
            "name=proj,path=/path/to/proj2",
            "--reference-project",
            "name=proj,path=/path/to/proj3",
        ]

        with patch("sys.argv", test_args):
            with patch("mcp_workspace.main.setup_logging"):
                from mcp_workspace.main import main

                main()

                # Verify run_server was called with correct arguments
                mock_run_server.assert_called_once()
                call_args = mock_run_server.call_args

                # Check project_dir argument (positional)
                assert call_args[0][0] == Path("/test/project").resolve()

                # Check reference_projects argument with auto-rename
                ref_projects = call_args[1]["reference_projects"]
                assert "proj" in ref_projects
                assert "proj_2" in ref_projects
                assert "proj_3" in ref_projects
                assert isinstance(ref_projects["proj"], ReferenceProject)
                assert ref_projects["proj"].path == Path("/path/to/proj1").resolve()
                assert ref_projects["proj_2"].path == Path("/path/to/proj2").resolve()
                assert ref_projects["proj_3"].path == Path("/path/to/proj3").resolve()

    @patch("mcp_workspace.main.detect_and_verify_url")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_main_url_mismatch_exits(
        self,
        mock_is_dir: MagicMock,
        mock_exists: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Test main() exits with code 1 on URL mismatch."""
        mock_exists.return_value = True
        mock_is_dir.return_value = True
        mock_detect.side_effect = ValueError(
            "URL mismatch for 'proj': explicit 'a' != detected 'b'"
        )

        test_args = [
            "script.py",
            "--project-dir",
            "/test/project",
            "--reference-project",
            "name=proj,path=/path/to/proj,url=https://wrong.com/repo",
        ]

        with patch("sys.argv", test_args):
            with patch("mcp_workspace.main.setup_logging"):
                from mcp_workspace.main import main

                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1

    @patch("mcp_workspace.server.run_server")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_main_file_size_limit_invalid_exits(
        self, mock_is_dir: MagicMock, mock_exists: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Test main() fails fast when --file-size-limit is <= 0."""
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        test_args = [
            "script.py",
            "--project-dir",
            "/test/project",
            "--file-size-limit",
            "0",
        ]

        with patch("sys.argv", test_args):
            with patch("mcp_workspace.main.setup_logging"):
                from mcp_workspace.main import main

                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
                mock_run_server.assert_not_called()

    @patch("mcp_workspace.server.run_server")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_main_passes_file_size_limit(
        self, mock_is_dir: MagicMock, mock_exists: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Test main() passes --file-size-limit through to run_server()."""
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        test_args = [
            "script.py",
            "--project-dir",
            "/test/project",
            "--file-size-limit",
            "750",
        ]

        with patch("sys.argv", test_args):
            with patch("mcp_workspace.main.setup_logging"):
                from mcp_workspace.main import main

                main()

                mock_run_server.assert_called_once()
                assert mock_run_server.call_args[1]["file_size_limit"] == 750

    @patch("mcp_workspace.server.run_server")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_main_file_size_limit_default_none(
        self, mock_is_dir: MagicMock, mock_exists: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Test main() passes file_size_limit=None when the flag is omitted."""
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        test_args = ["script.py", "--project-dir", "/test/project"]

        with patch("sys.argv", test_args):
            with patch("mcp_workspace.main.setup_logging"):
                from mcp_workspace.main import main

                main()

                mock_run_server.assert_called_once()
                assert mock_run_server.call_args[1]["file_size_limit"] is None
