"""Tests for the MCP server review-gate default resolution and threading.

Covers the ``set_fail_on_reviews`` setter, ``run_server`` threading the
``fail_on_reviews`` default through to it, and ``check_branch_status``
resolving the ``Optional[bool]`` tri-state (per-call override vs. the
configured server default) into a plain bool passed downstream.
"""

from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, patch

import pytest

import mcp_workspace.server as server_module
from mcp_workspace.server import (
    check_branch_status,
    run_server,
    set_fail_on_reviews,
    set_project_dir,
)


class TestSetFailOnReviews:
    """Test the module-level review-gate default setter."""

    @pytest.fixture(autouse=True)
    def _reset_global(self) -> Generator[None, None, None]:
        """Reset the module-level review-gate default after each test."""
        yield
        server_module._fail_on_reviews = False

    def test_set_fail_on_reviews_sets_global(self) -> None:
        """set_fail_on_reviews(True) sets the module global to True."""
        set_fail_on_reviews(True)
        assert server_module._fail_on_reviews is True


class TestRunServerFailOnReviews:
    """Test that run_server threads fail_on_reviews to set_fail_on_reviews."""

    def test_run_server_threads_fail_on_reviews(self) -> None:
        """run_server passes fail_on_reviews through to the setter."""
        with patch("mcp_workspace.server.mcp.run"):
            with patch("mcp_workspace.server.set_project_dir"):
                with patch(
                    "mcp_workspace.server.set_fail_on_reviews"
                ) as mock_setter:
                    run_server(Path("/test/project"), fail_on_reviews=True)

        mock_setter.assert_called_once_with(True)

    def test_run_server_default_is_false(self) -> None:
        """run_server defaults fail_on_reviews to False when omitted."""
        with patch("mcp_workspace.server.mcp.run"):
            with patch("mcp_workspace.server.set_project_dir"):
                with patch(
                    "mcp_workspace.server.set_fail_on_reviews"
                ) as mock_setter:
                    run_server(Path("/test/project"))

        mock_setter.assert_called_once_with(False)


class TestCheckBranchStatusTriState:
    """Test the Optional[bool] tri-state resolution in check_branch_status."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> Generator[None, None, None]:
        """Set a project dir and reset the review-gate default after each test."""
        set_project_dir(tmp_path)
        yield
        server_module._fail_on_reviews = False

    @pytest.mark.asyncio
    async def test_none_uses_server_default(self) -> None:
        """fail_on_reviews=None falls back to the server default."""
        server_module._fail_on_reviews = True
        with patch(
            "mcp_workspace.checks.branch_status_polling.async_poll_branch_status",
            new_callable=AsyncMock,
            return_value="report",
        ) as mock_poll:
            await check_branch_status(fail_on_reviews=None)

        assert mock_poll.await_args.kwargs["fail_on_reviews"] is True

    @pytest.mark.asyncio
    async def test_false_overrides_true_default(self) -> None:
        """Explicit fail_on_reviews=False overrides a True server default."""
        server_module._fail_on_reviews = True
        with patch(
            "mcp_workspace.checks.branch_status_polling.async_poll_branch_status",
            new_callable=AsyncMock,
            return_value="report",
        ) as mock_poll:
            await check_branch_status(fail_on_reviews=False)

        assert mock_poll.await_args.kwargs["fail_on_reviews"] is False

    @pytest.mark.asyncio
    async def test_true_overrides_false_default(self) -> None:
        """Explicit fail_on_reviews=True overrides a False server default."""
        server_module._fail_on_reviews = False
        with patch(
            "mcp_workspace.checks.branch_status_polling.async_poll_branch_status",
            new_callable=AsyncMock,
            return_value="report",
        ) as mock_poll:
            await check_branch_status(fail_on_reviews=True)

        assert mock_poll.await_args.kwargs["fail_on_reviews"] is True
