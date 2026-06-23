"""Tests for git() with reference project support."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


class TestGitReferenceProject:
    """Tests for git() with reference_name parameter."""

    @pytest.mark.asyncio
    async def test_git_valid_reference_project(self) -> None:
        """Mock get_reference_project_path returning a Path and git_impl;
        verify git_impl called with reference project path as project_dir."""
        from mcp_workspace.server import git

        ref_path = Path("/tmp/ref_project").resolve()

        with patch(
            "mcp_workspace.server.get_reference_project_path",
            new_callable=AsyncMock,
            return_value=ref_path,
        ) as mock_get_path:
            with patch(
                "mcp_workspace.git_operations.read_operations.git"
            ) as mock_git_impl:
                mock_git_impl.return_value = "commit abc123"

                result = await git(
                    command="log",
                    args=["--oneline"],
                    reference_name="my_ref",
                )

                assert result == "commit abc123"
                mock_get_path.assert_awaited_once_with("my_ref")
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
    async def test_git_invalid_reference_project(self) -> None:
        """Mock get_reference_project_path raising ValueError; verify error propagates."""
        from mcp_workspace.server import git

        with patch(
            "mcp_workspace.server.get_reference_project_path",
            new_callable=AsyncMock,
            side_effect=ValueError("Reference project 'bad' not found"),
        ):
            with pytest.raises(ValueError, match="Reference project 'bad' not found"):
                await git(command="log", reference_name="bad")

    @pytest.mark.asyncio
    async def test_git_ensure_available_before_git_runs(self) -> None:
        """Verify get_reference_project_path is awaited before git_impl executes."""
        from mcp_workspace.server import git

        ref_path = Path("/tmp/ref_project").resolve()
        call_order: list[str] = []

        async def mock_get_path(name: str) -> Path:
            call_order.append("get_reference_project_path")
            return ref_path

        def mock_git_impl_fn(**kwargs: object) -> str:
            call_order.append("git_impl")
            return "output"

        with patch(
            "mcp_workspace.server.get_reference_project_path",
            side_effect=mock_get_path,
        ):
            with patch(
                "mcp_workspace.git_operations.read_operations.git",
                side_effect=mock_git_impl_fn,
            ):
                await git(command="status", reference_name="proj")

        assert call_order == ["get_reference_project_path", "git_impl"]

    @pytest.mark.asyncio
    async def test_git_without_reference_name_uses_project_dir(self) -> None:
        """No reference_name passed; verify git_impl is called with _project_dir."""
        import mcp_workspace.server as server_module
        from mcp_workspace.server import git

        original_project_dir = server_module._project_dir
        test_dir = Path("/tmp/workspace").resolve()
        server_module._project_dir = test_dir

        try:
            with patch(
                "mcp_workspace.git_operations.read_operations.git"
            ) as mock_git_impl:
                mock_git_impl.return_value = "status output"

                result = await git(command="status")

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
        finally:
            server_module._project_dir = original_project_dir
