"""Tests for the MCP server review-gate default resolution and threading.

Covers ``run_server`` threading the ``fail_on_reviews`` default through to
``tool_specs``, and ``check_branch_status`` resolving the ``Optional[bool]``
tri-state (per-call override vs. the configured server default) into a plain
bool passed downstream.
"""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mcp_workspace.server import run_server
from tests.conftest import ToolMap

POLL = "mcp_workspace.checks.branch_status_polling.async_poll_branch_status"


class TestRunServerFailOnReviews:
    """Test that run_server threads fail_on_reviews to tool_specs."""

    def test_run_server_threads_fail_on_reviews(self, tmp_path: Path) -> None:
        """run_server passes fail_on_reviews through to tool_specs."""
        with patch("mcp_workspace.server.FastMCP.run"):
            with patch(
                "mcp_workspace.server.tool_specs", return_value=()
            ) as mock_specs:
                run_server(tmp_path, fail_on_reviews=True)

        assert mock_specs.call_args.args == (tmp_path,)
        assert mock_specs.call_args.kwargs["fail_on_reviews"] is True

    def test_run_server_default_is_false(self, tmp_path: Path) -> None:
        """run_server defaults fail_on_reviews to False when omitted."""
        with patch("mcp_workspace.server.FastMCP.run"):
            with patch(
                "mcp_workspace.server.tool_specs", return_value=()
            ) as mock_specs:
                run_server(tmp_path)

        assert mock_specs.call_args.kwargs["fail_on_reviews"] is False


class TestCheckBranchStatusTriState:
    """Test the Optional[bool] tri-state resolution in check_branch_status."""

    @pytest.mark.asyncio
    async def test_none_uses_server_default(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """fail_on_reviews=None falls back to the server default."""
        tools = make_tools(fail_on_reviews=True)
        with patch(POLL, new_callable=AsyncMock, return_value="report") as mock_poll:
            await tools["check_branch_status"](fail_on_reviews=None)

        assert mock_poll.await_args.kwargs["fail_on_reviews"] is True

    @pytest.mark.asyncio
    async def test_false_overrides_true_default(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Explicit fail_on_reviews=False overrides a True server default."""
        tools = make_tools(fail_on_reviews=True)
        with patch(POLL, new_callable=AsyncMock, return_value="report") as mock_poll:
            await tools["check_branch_status"](fail_on_reviews=False)

        assert mock_poll.await_args.kwargs["fail_on_reviews"] is False

    @pytest.mark.asyncio
    async def test_true_overrides_false_default(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Explicit fail_on_reviews=True overrides a False server default."""
        tools = make_tools(fail_on_reviews=False)
        with patch(POLL, new_callable=AsyncMock, return_value="report") as mock_poll:
            await tools["check_branch_status"](fail_on_reviews=True)

        assert mock_poll.await_args.kwargs["fail_on_reviews"] is True
