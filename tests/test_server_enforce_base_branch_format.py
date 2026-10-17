"""Tests for the MCP server's --enforce-base-branch-format flag plumbing.

Covers the ``set_enforce_base_branch_format`` setter and ``run_server``
threading the ``enforce_base_branch_format`` default through to it.
"""

from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest

import mcp_workspace.server as server_module
from mcp_workspace.server import run_server, set_enforce_base_branch_format


class TestSetEnforceBaseBranchFormat:
    """Test the module-level base-branch-format enforcement default setter."""

    @pytest.fixture(autouse=True)
    def _reset_global(self) -> Generator[None, None, None]:
        """Reset the module-level enforcement default after each test."""
        yield
        server_module._enforce_base_branch_format = True

    def test_set_enforce_base_branch_format_sets_global(self) -> None:
        """set_enforce_base_branch_format(False) sets the module global to False."""
        set_enforce_base_branch_format(False)
        assert server_module._enforce_base_branch_format is False


class TestRunServerEnforceBaseBranchFormat:
    """Test that run_server threads enforce_base_branch_format to its setter."""

    def test_run_server_threads_enforce_base_branch_format(self) -> None:
        """run_server passes enforce_base_branch_format through to the setter."""
        with patch("mcp_workspace.server.mcp.run"):
            with patch("mcp_workspace.server.set_project_dir"):
                with patch(
                    "mcp_workspace.server.set_enforce_base_branch_format"
                ) as mock_setter:
                    run_server(Path("/test/project"), enforce_base_branch_format=False)

        mock_setter.assert_called_once_with(False)

    def test_run_server_default_is_true(self) -> None:
        """run_server defaults enforce_base_branch_format to True when omitted."""
        with patch("mcp_workspace.server.mcp.run"):
            with patch("mcp_workspace.server.set_project_dir"):
                with patch(
                    "mcp_workspace.server.set_enforce_base_branch_format"
                ) as mock_setter:
                    run_server(Path("/test/project"))

        mock_setter.assert_called_once_with(True)
