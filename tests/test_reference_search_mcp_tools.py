"""Tests for the search_reference_files MCP tool."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mcp_workspace.reference_projects import ReferenceProject


class TestSearchReferenceFiles:
    """Test search_reference_files MCP tool."""

    @pytest.mark.asyncio
    async def test_search_by_glob(self) -> None:
        """Test file search by glob pattern delegates to search_files_util."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import search_reference_files

        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        server_module._reference_projects = test_projects

        with patch(
            "mcp_workspace.server_reference_tools.search_files_util"
        ) as mock_search:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_search.return_value = {
                    "mode": "file_search",
                    "files": ["src/main.py", "src/utils.py"],
                    "total_files": 2,
                    "truncated": False,
                }

                result = await search_reference_files("test_proj", glob="**/*.py")

                assert result["mode"] == "file_search"
                assert result["total_files"] == 2
                mock_search.assert_called_once_with(
                    project_dir=ref_path,
                    glob="**/*.py",
                    pattern=None,
                    context_lines=0,
                    max_results=50,
                    max_result_lines=200,
                )

    @pytest.mark.asyncio
    async def test_search_by_pattern(self) -> None:
        """Test content search by regex pattern."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import search_reference_files

        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        server_module._reference_projects = test_projects

        with patch(
            "mcp_workspace.server_reference_tools.search_files_util"
        ) as mock_search:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_search.return_value = {
                    "mode": "content_search",
                    "matches": [
                        {"file": "src/main.py", "line": 1, "text": "def foo():"}
                    ],
                    "total_matches": 1,
                    "truncated": False,
                }

                result = await search_reference_files("test_proj", pattern="def foo")

                assert result["mode"] == "content_search"
                assert result["total_matches"] == 1
                mock_search.assert_called_once_with(
                    project_dir=ref_path,
                    glob=None,
                    pattern="def foo",
                    context_lines=0,
                    max_results=50,
                    max_result_lines=200,
                )

    @pytest.mark.asyncio
    async def test_search_combined(self) -> None:
        """Test combined glob + pattern search."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import search_reference_files

        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        server_module._reference_projects = test_projects

        with patch(
            "mcp_workspace.server_reference_tools.search_files_util"
        ) as mock_search:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_search.return_value = {
                    "mode": "content_search",
                    "matches": [],
                    "total_matches": 0,
                    "truncated": False,
                }

                result = await search_reference_files(
                    "test_proj", glob="**/*.py", pattern="import os"
                )

                assert result["mode"] == "content_search"
                mock_search.assert_called_once_with(
                    project_dir=ref_path,
                    glob="**/*.py",
                    pattern="import os",
                    context_lines=0,
                    max_results=50,
                    max_result_lines=200,
                )

    @pytest.mark.asyncio
    async def test_search_not_found_project(self) -> None:
        """Test error for non-existent reference project."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import search_reference_files

        server_module._reference_projects = {}

        with pytest.raises(
            ValueError, match="Reference project 'nonexistent' not found"
        ):
            await search_reference_files("nonexistent", glob="**/*.py")

    @pytest.mark.asyncio
    async def test_search_calls_ensure_available(self) -> None:
        """Verify ensure_available is awaited before search."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import search_reference_files

        ref_path = Path("/tmp/test_project").resolve()
        proj = ReferenceProject(name="test_proj", path=ref_path)
        server_module._reference_projects = {"test_proj": proj}

        with patch(
            "mcp_workspace.server_reference_tools.search_files_util"
        ) as mock_search:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_ensure:
                mock_search.return_value = {
                    "mode": "file_search",
                    "files": [],
                    "total_files": 0,
                    "truncated": False,
                }

                await search_reference_files("test_proj", glob="*.py")

                mock_ensure.assert_awaited_once_with(proj)
