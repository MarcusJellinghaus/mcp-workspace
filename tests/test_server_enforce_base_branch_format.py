"""Tests for the MCP server's --enforce-base-branch-format flag plumbing.

Covers the ``set_enforce_base_branch_format`` setter and ``run_server``
threading the ``enforce_base_branch_format`` default through to it.
"""

from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest

import mcp_workspace.server as server_module
from mcp_workspace.server import (
    _check_base_branch,
    run_server,
    set_enforce_base_branch_format,
)


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


class TestCheckBaseBranch:
    """Test the _check_base_branch helper."""

    @pytest.fixture(autouse=True)
    def _reset_global(self) -> Generator[None, None, None]:
        """Reset the module-level enforcement default after each test."""
        yield
        server_module._enforce_base_branch_format = True

    def test_absent_section_is_none(self) -> None:
        """A body with no Base Branch section returns None."""
        assert _check_base_branch("### Description\n\nx") is None

    def test_no_body_is_none(self) -> None:
        """A None body returns None."""
        assert _check_base_branch(None) is None

    def test_empty_section_is_none(self) -> None:
        """An empty Base Branch section returns None."""
        assert _check_base_branch("### Base Branch\n\n### Next") is None

    def test_valid_single_line_is_none(self) -> None:
        """A valid single-line Base Branch section returns None."""
        assert (
            _check_base_branch("### Base Branch\n\nfeature/v2\n\n### Description")
            is None
        )

    def test_malformed_returns_error_with_first_line(self) -> None:
        """A multi-line Base Branch section returns an error naming the issue."""
        result = _check_base_branch("### Base Branch\n\nline1\nline2\n")
        assert result is not None
        assert "### Base Branch" in result
        assert "one line" in result
        assert "line1" in result
        assert "line2" not in result

    def test_crlf_malformed_is_rejected(self) -> None:
        """A CRLF multi-line section embeds the first line without a trailing \\r."""
        result = _check_base_branch("### Base Branch\r\n\r\nline1\r\nline2\r\n")
        assert result is not None
        assert "line1" in result
        assert "line1\r" not in result

    def test_crlf_valid_is_accepted(self) -> None:
        """A CRLF single-line Base Branch section returns None."""
        assert _check_base_branch("### Base Branch\r\n\r\nfeature/v2\r\n") is None

    def test_fenced_heading_is_none(self) -> None:
        """A Base Branch heading quoted only inside a code fence returns None."""
        body = "### Description\n\n```\n### Base Branch\n\nline1\nline2\n```\n"
        assert _check_base_branch(body) is None

    def test_flag_off_always_none(self) -> None:
        """When the flag is off, even a malformed section returns None."""
        server_module._enforce_base_branch_format = False
        assert _check_base_branch("### Base Branch\n\nline1\nline2\n") is None
