"""Tests for git() with reference project support."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import ANY, AsyncMock, patch

import pytest

from mcp_workspace.toolset._context import WorkspaceContext
from tests.conftest import ToolMap


class TestGitReferenceProject:
    """Tests for git() with reference_name parameter."""

    @pytest.mark.asyncio
    async def test_git_valid_reference_project(self, tools: ToolMap) -> None:
        """Mock reference_project_path returning a Path and git_impl;
        verify git_impl called with reference project path as project_dir."""
        ref_path = Path("/tmp/ref_project").resolve()

        with patch(
            "mcp_workspace.toolset.git.reference_project_path",
            new_callable=AsyncMock,
            return_value=ref_path,
        ) as mock_get_path:
            with patch(
                "mcp_workspace.git_operations.read_operations.git"
            ) as mock_git_impl:
                mock_git_impl.return_value = "commit abc123"

                result = await tools["git"](
                    command="log",
                    args=["--oneline"],
                    reference_name="my_ref",
                )

                assert result == "commit abc123"
                mock_get_path.assert_awaited_once_with(ANY, "my_ref")
                mock_git_impl.assert_called_once_with(
                    command="log",
                    project_dir=ref_path,
                    args=["--oneline"],
                    pathspec=None,
                    search=None,
                    context=3,
                    max_lines=None,
                    compact=True,
                )

    @pytest.mark.asyncio
    async def test_git_invalid_reference_project(self, tools: ToolMap) -> None:
        """Mock reference_project_path raising ValueError; verify error propagates."""
        with patch(
            "mcp_workspace.toolset.git.reference_project_path",
            new_callable=AsyncMock,
            side_effect=ValueError("Reference project 'bad' not found"),
        ):
            with pytest.raises(ValueError, match="Reference project 'bad' not found"):
                await tools["git"](command="log", reference_name="bad")

    @pytest.mark.asyncio
    async def test_git_ensure_available_before_git_runs(self, tools: ToolMap) -> None:
        """Verify reference_project_path is awaited before git_impl executes."""
        ref_path = Path("/tmp/ref_project").resolve()
        call_order: list[str] = []

        async def mock_get_path(ctx: WorkspaceContext, name: str) -> Path:
            call_order.append("reference_project_path")
            return ref_path

        def mock_git_impl_fn(**kwargs: object) -> str:
            call_order.append("git_impl")
            return "output"

        with patch(
            "mcp_workspace.toolset.git.reference_project_path",
            side_effect=mock_get_path,
        ):
            with patch(
                "mcp_workspace.git_operations.read_operations.git",
                side_effect=mock_git_impl_fn,
            ):
                await tools["git"](command="status", reference_name="proj")

        assert call_order == ["reference_project_path", "git_impl"]

    @pytest.mark.asyncio
    async def test_git_without_reference_name_uses_project_dir(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """No reference_name passed; verify git_impl is called with project_dir."""
        test_dir = Path("/tmp/workspace").resolve()
        tools = make_tools(test_dir)

        with patch("mcp_workspace.git_operations.read_operations.git") as mock_git_impl:
            mock_git_impl.return_value = "status output"

            result = await tools["git"](command="status")

            assert result == "status output"
            mock_git_impl.assert_called_once_with(
                command="status",
                project_dir=test_dir,
                args=None,
                pathspec=None,
                search=None,
                context=3,
                max_lines=None,
                compact=True,
            )
