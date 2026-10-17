"""Tests for main.py: CLI argument parsing and main() integration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.main import main, parse_args
from mcp_workspace.reference_projects import ReferenceProject


class TestParseArgs:
    """Test CLI argument parsing."""

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

    def test_parse_fail_on_reviews(self) -> None:
        """Test parsing the --fail-on-reviews flag sets True."""
        with patch(
            "sys.argv",
            [
                "script.py",
                "--project-dir",
                "/tmp",
                "--fail-on-reviews",
            ],
        ):
            args = parse_args()
            assert args.fail_on_reviews is True

    def test_parse_fail_on_reviews_default(self) -> None:
        """Test --fail-on-reviews defaults to False when omitted."""
        with patch("sys.argv", ["script.py", "--project-dir", "/tmp"]):
            args = parse_args()
            assert args.fail_on_reviews is False

    def test_parse_enforce_base_branch_format_default(self) -> None:
        """Test --enforce-base-branch-format defaults to True when omitted."""
        with patch("sys.argv", ["script.py", "--project-dir", "/tmp"]):
            args = parse_args()
            assert args.enforce_base_branch_format is True

    def test_parse_no_enforce_base_branch_format(self) -> None:
        """Test --no-enforce-base-branch-format sets the flag to False."""
        with patch(
            "sys.argv",
            [
                "script.py",
                "--project-dir",
                "/tmp",
                "--no-enforce-base-branch-format",
            ],
        ):
            args = parse_args()
            assert args.enforce_base_branch_format is False


class TestMain:
    """Test CLI to server integration via main()."""

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
                main()

                mock_run_server.assert_called_once()
                assert mock_run_server.call_args[1]["file_size_limit"] is None

    @patch("mcp_workspace.server.run_server")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_main_passes_fail_on_reviews(
        self, mock_is_dir: MagicMock, mock_exists: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Test main() passes --fail-on-reviews through to run_server()."""
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        test_args = [
            "script.py",
            "--project-dir",
            "/test/project",
            "--fail-on-reviews",
        ]

        with patch("sys.argv", test_args):
            with patch("mcp_workspace.main.setup_logging"):
                main()

                mock_run_server.assert_called_once()
                assert mock_run_server.call_args[1]["fail_on_reviews"] is True

    @patch("mcp_workspace.server.run_server")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_main_fail_on_reviews_default_false(
        self, mock_is_dir: MagicMock, mock_exists: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Test main() passes fail_on_reviews=False when the flag is omitted."""
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        test_args = ["script.py", "--project-dir", "/test/project"]

        with patch("sys.argv", test_args):
            with patch("mcp_workspace.main.setup_logging"):
                main()

                mock_run_server.assert_called_once()
                assert mock_run_server.call_args[1]["fail_on_reviews"] is False

    @patch("mcp_workspace.server.run_server")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_main_passes_no_enforce_base_branch_format(
        self, mock_is_dir: MagicMock, mock_exists: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Test main() passes --no-enforce-base-branch-format through to run_server()."""
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        test_args = [
            "script.py",
            "--project-dir",
            "/test/project",
            "--no-enforce-base-branch-format",
        ]

        with patch("sys.argv", test_args):
            with patch("mcp_workspace.main.setup_logging"):
                main()

                mock_run_server.assert_called_once()
                assert (
                    mock_run_server.call_args[1]["enforce_base_branch_format"] is False
                )

    @patch("mcp_workspace.server.run_server")
    @patch("mcp_workspace.main.Path.exists")
    @patch("mcp_workspace.main.Path.is_dir")
    def test_main_enforce_base_branch_format_default_true(
        self, mock_is_dir: MagicMock, mock_exists: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Test main() passes enforce_base_branch_format=True when the flag is omitted."""
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        test_args = ["script.py", "--project-dir", "/test/project"]

        with patch("sys.argv", test_args):
            with patch("mcp_workspace.main.setup_logging"):
                main()

                mock_run_server.assert_called_once()
                assert (
                    mock_run_server.call_args[1]["enforce_base_branch_format"] is True
                )
