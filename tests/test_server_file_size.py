"""Tests for the MCP server file-size limit resolution and threading.

Covers ``check_file_size`` default-limit resolution (explicit ``max_lines``
vs. the configured ``--file-size-limit`` flag vs. the 600 fallback) and that
``run_server`` threads ``file_size_limit`` through to ``tool_specs``.
"""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

from mcp_workspace.server import run_server
from tests.conftest import ToolMap


class TestCheckFileSizeLimit:
    """Test the per-project default limit resolution for check_file_size."""

    def test_explicit_max_lines_overrides_flag(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Explicit max_lines wins over the configured flag value."""
        tools = make_tools(file_size_limit=750)

        with patch("mcp_workspace.toolset.checks.check_file_sizes") as mock_check:
            with patch("mcp_workspace.toolset.checks.render_output") as mock_render:
                tools["check_file_size"](500)

        assert mock_check.call_args.kwargs["max_lines"] == 500
        assert mock_render.call_args.args[1] == 500

    def test_flag_used_when_omitted(self, make_tools: Callable[..., ToolMap]) -> None:
        """The configured flag value is used when max_lines is omitted."""
        tools = make_tools(file_size_limit=750)

        with patch("mcp_workspace.toolset.checks.check_file_sizes") as mock_check:
            with patch("mcp_workspace.toolset.checks.render_output") as mock_render:
                tools["check_file_size"]()

        assert mock_check.call_args.kwargs["max_lines"] == 750
        assert mock_render.call_args.args[1] == 750

    def test_fallback_to_600(self, make_tools: Callable[..., ToolMap]) -> None:
        """Falls back to 600 when neither max_lines nor the flag are set."""
        tools = make_tools(file_size_limit=None)

        with patch("mcp_workspace.toolset.checks.check_file_sizes") as mock_check:
            with patch("mcp_workspace.toolset.checks.render_output") as mock_render:
                tools["check_file_size"]()

        assert mock_check.call_args.kwargs["max_lines"] == 600
        assert mock_render.call_args.args[1] == 600


class TestCheckFileSizeShowAllowlisted:
    """Test routing of check_file_size's show_allowlisted flag."""

    def test_show_allowlisted_routes_to_render_allowlisted(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        """The flag lists the allowlist and skips the default check."""
        tools = make_tools(tmp_path, file_size_limit=750)

        with patch("mcp_workspace.toolset.checks.check_file_sizes") as mock_check:
            with patch("mcp_workspace.toolset.checks.render_output") as mock_render:
                with patch(
                    "mcp_workspace.toolset.checks.render_allowlisted",
                    return_value="listing",
                ) as mock_listed:
                    result = tools["check_file_size"](show_allowlisted=True)

        assert result == "listing"
        assert mock_listed.call_args.args[0] == tmp_path
        assert mock_listed.call_args.args[1] == 750
        mock_check.assert_not_called()
        mock_render.assert_not_called()

    def test_default_call_does_not_list_allowlist(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Without the flag, the default check and report run."""
        tools = make_tools(file_size_limit=None)

        with patch("mcp_workspace.toolset.checks.check_file_sizes") as mock_check:
            with patch("mcp_workspace.toolset.checks.render_output") as mock_render:
                with patch(
                    "mcp_workspace.toolset.checks.render_allowlisted"
                ) as mock_listed:
                    tools["check_file_size"]()

        mock_check.assert_called_once()
        mock_render.assert_called_once()
        mock_listed.assert_not_called()


class TestRunServerFileSizeLimit:
    """Test that run_server threads file_size_limit to tool_specs."""

    def test_run_server_threads_value(self, tmp_path: Path) -> None:
        """run_server passes the file_size_limit through to tool_specs."""
        with patch("mcp_workspace.server.FastMCP.run"):
            with patch(
                "mcp_workspace.server.tool_specs", return_value=()
            ) as mock_specs:
                run_server(tmp_path, file_size_limit=750)

        assert mock_specs.call_args.args == (tmp_path,)
        assert mock_specs.call_args.kwargs["file_size_limit"] == 750

    def test_run_server_default_is_none(self, tmp_path: Path) -> None:
        """run_server defaults file_size_limit to None when omitted."""
        with patch("mcp_workspace.server.FastMCP.run"):
            with patch(
                "mcp_workspace.server.tool_specs", return_value=()
            ) as mock_specs:
                run_server(tmp_path)

        assert mock_specs.call_args.kwargs["file_size_limit"] is None
