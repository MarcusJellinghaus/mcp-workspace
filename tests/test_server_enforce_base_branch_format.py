"""Tests for the MCP server's --enforce-base-branch-format flag plumbing.

Covers ``run_server`` threading the ``enforce_base_branch_format`` default
through to ``tool_specs``, and the ``check_base_branch`` helper that reads it.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_workspace.server import run_server
from mcp_workspace.toolset._context import WorkspaceContext
from mcp_workspace.toolset._github_write_helpers import check_base_branch


class TestRunServerEnforceBaseBranchFormat:
    """Test that run_server threads enforce_base_branch_format to tool_specs."""

    def test_run_server_threads_enforce_base_branch_format(
        self, tmp_path: Path
    ) -> None:
        """run_server passes enforce_base_branch_format through to tool_specs."""
        with patch("mcp_workspace.server.FastMCP.run"):
            with patch(
                "mcp_workspace.server.tool_specs", return_value=()
            ) as mock_specs:
                run_server(tmp_path, enforce_base_branch_format=False)

        assert mock_specs.call_args.args == (tmp_path,)
        assert mock_specs.call_args.kwargs["enforce_base_branch_format"] is False

    def test_run_server_default_is_true(self, tmp_path: Path) -> None:
        """run_server defaults enforce_base_branch_format to True when omitted."""
        with patch("mcp_workspace.server.FastMCP.run"):
            with patch(
                "mcp_workspace.server.tool_specs", return_value=()
            ) as mock_specs:
                run_server(tmp_path)

        assert mock_specs.call_args.kwargs["enforce_base_branch_format"] is True


@pytest.fixture
def ctx(tmp_path: Path) -> WorkspaceContext:
    """Context with the Base Branch format check enabled."""
    return WorkspaceContext(tmp_path, {}, None, None, False, True)


@pytest.fixture
def ctx_off(tmp_path: Path) -> WorkspaceContext:
    """Context with the Base Branch format check disabled."""
    return WorkspaceContext(tmp_path, {}, None, None, False, False)


class TestCheckBaseBranch:
    """Test the check_base_branch helper."""

    def test_absent_section_is_none(self, ctx: WorkspaceContext) -> None:
        """A body with no Base Branch section returns None."""
        assert check_base_branch(ctx, "### Description\n\nx") is None

    def test_no_body_is_none(self, ctx: WorkspaceContext) -> None:
        """A None body returns None."""
        assert check_base_branch(ctx, None) is None

    def test_empty_section_is_none(self, ctx: WorkspaceContext) -> None:
        """An empty Base Branch section returns None."""
        assert check_base_branch(ctx, "### Base Branch\n\n### Next") is None

    def test_valid_single_line_is_none(self, ctx: WorkspaceContext) -> None:
        """A valid single-line Base Branch section returns None."""
        assert (
            check_base_branch(ctx, "### Base Branch\n\nfeature/v2\n\n### Description")
            is None
        )

    def test_malformed_returns_error_with_first_line(
        self, ctx: WorkspaceContext
    ) -> None:
        """A multi-line Base Branch section returns an error naming the issue."""
        result = check_base_branch(ctx, "### Base Branch\n\nline1\nline2\n")
        assert result is not None
        assert "### Base Branch" in result
        assert "one line" in result
        assert "line1" in result
        assert "line2" not in result

    def test_invalid_ref_returns_error(self, ctx: WorkspaceContext) -> None:
        """A single-line Base Branch value that is not a valid ref is rejected."""
        result = check_base_branch(ctx, "### Base Branch\n\nmain branch\n")
        assert result is not None
        assert result.startswith("Error: ")
        assert "valid git branch name" in result
        assert "'main branch'" in result

    def test_invalid_ref_flag_off_is_none(self, ctx_off: WorkspaceContext) -> None:
        """When the flag is off, an invalid ref returns None."""
        assert check_base_branch(ctx_off, "### Base Branch\n\nmain branch\n") is None

    def test_crlf_malformed_is_rejected(self, ctx: WorkspaceContext) -> None:
        """A CRLF multi-line section embeds the first line without a trailing \\r."""
        result = check_base_branch(ctx, "### Base Branch\r\n\r\nline1\r\nline2\r\n")
        assert result is not None
        assert "line1" in result
        assert "line1\r" not in result

    def test_crlf_valid_is_accepted(self, ctx: WorkspaceContext) -> None:
        """A CRLF single-line Base Branch section returns None."""
        assert check_base_branch(ctx, "### Base Branch\r\n\r\nfeature/v2\r\n") is None

    def test_fenced_heading_is_none(self, ctx: WorkspaceContext) -> None:
        """A Base Branch heading quoted only inside a code fence returns None."""
        body = "### Description\n\n```\n### Base Branch\n\nline1\nline2\n```\n"
        assert check_base_branch(ctx, body) is None

    def test_flag_off_always_none(self, ctx_off: WorkspaceContext) -> None:
        """When the flag is off, even a malformed section returns None."""
        assert check_base_branch(ctx_off, "### Base Branch\n\nline1\nline2\n") is None
