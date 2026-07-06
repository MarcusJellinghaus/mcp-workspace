"""Tests for the MCP server file-size limit resolution and threading.

Covers ``check_file_size`` default-limit resolution (explicit ``max_lines``
vs. the configured ``--file-size-limit`` flag vs. the 600 fallback) and that
``run_server`` threads ``file_size_limit`` through to ``set_file_size_limit``.
"""

from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest

import mcp_workspace.server as server_module
from mcp_workspace.server import (
    check_file_size,
    run_server,
    set_file_size_limit,
    set_project_dir,
)


@pytest.fixture(autouse=True)
def setup_server(project_dir: Path) -> Generator[None, None, None]:
    """Setup the server with the project directory."""
    set_project_dir(project_dir)
    yield


class TestCheckFileSizeLimit:
    """Test the per-project default limit resolution for check_file_size."""

    @pytest.fixture(autouse=True)
    def _reset_globals(self) -> Generator[None, None, None]:
        """Reset the module-level file size limit after each test."""
        yield
        server_module._file_size_limit = None

    def test_explicit_max_lines_overrides_flag(self, tmp_path: Path) -> None:
        """Explicit max_lines wins over the configured flag value."""
        set_project_dir(tmp_path)
        set_file_size_limit(750)

        with patch("mcp_workspace.server.check_file_sizes") as mock_check:
            with patch("mcp_workspace.server.render_output") as mock_render:
                check_file_size(500)

        assert mock_check.call_args.kwargs["max_lines"] == 500
        assert mock_render.call_args.args[1] == 500

    def test_flag_used_when_omitted(self, tmp_path: Path) -> None:
        """The configured flag value is used when max_lines is omitted."""
        set_project_dir(tmp_path)
        set_file_size_limit(750)

        with patch("mcp_workspace.server.check_file_sizes") as mock_check:
            with patch("mcp_workspace.server.render_output") as mock_render:
                check_file_size()

        assert mock_check.call_args.kwargs["max_lines"] == 750
        assert mock_render.call_args.args[1] == 750

    def test_fallback_to_600(self, tmp_path: Path) -> None:
        """Falls back to 600 when neither max_lines nor the flag are set."""
        set_project_dir(tmp_path)
        set_file_size_limit(None)

        with patch("mcp_workspace.server.check_file_sizes") as mock_check:
            with patch("mcp_workspace.server.render_output") as mock_render:
                check_file_size()

        assert mock_check.call_args.kwargs["max_lines"] == 600
        assert mock_render.call_args.args[1] == 600


class TestRunServerFileSizeLimit:
    """Test that run_server threads file_size_limit to set_file_size_limit."""

    def test_run_server_threads_value(self) -> None:
        """run_server passes the file_size_limit through to the setter."""
        with patch("mcp_workspace.server.mcp.run"):
            with patch("mcp_workspace.server.set_file_size_limit") as mock_setter:
                run_server(Path("/test/project"), file_size_limit=750)

        mock_setter.assert_called_once_with(750)

    def test_run_server_default_is_none(self) -> None:
        """run_server defaults file_size_limit to None when omitted."""
        with patch("mcp_workspace.server.mcp.run"):
            with patch("mcp_workspace.server.set_file_size_limit") as mock_setter:
                run_server(Path("/test/project"))

        mock_setter.assert_called_once_with(None)
