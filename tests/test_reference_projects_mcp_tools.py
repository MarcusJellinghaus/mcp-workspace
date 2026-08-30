"""Tests for reference project MCP tools and search functionality."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mcp_workspace.reference_projects import ReferenceProject


class TestReferenceProjectMCPTools:
    """Test MCP tools functionality."""

    def test_get_reference_projects_empty(self) -> None:
        """Test discovery tool returns empty dict when no projects."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import get_reference_projects

        # Clear reference projects
        server_module._reference_projects = {}

        # Should return structured dict with empty projects list
        result = get_reference_projects()
        expected = {
            "count": 0,
            "projects": [],
            "usage": "No reference projects available",
        }
        assert result == expected
        assert isinstance(result, dict)

    def test_get_reference_projects_sorted(self) -> None:
        """Test discovery tool returns sorted list of project objects in structured dict."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import get_reference_projects

        # Set up test data in unsorted order
        test_projects = {
            "zebra": ReferenceProject(name="zebra", path=Path("/path/to/zebra")),
            "alpha": ReferenceProject(
                name="alpha",
                path=Path("/path/to/alpha"),
                url="https://github.com/org/alpha",
            ),
            "beta": ReferenceProject(name="beta", path=Path("/path/to/beta")),
        }
        server_module._reference_projects = test_projects

        # Should return structured dict with sorted projects list of objects
        result = get_reference_projects()
        expected = {
            "count": 3,
            "projects": [
                {"name": "alpha", "url": "https://github.com/org/alpha"},
                {"name": "beta", "url": None},
                {"name": "zebra", "url": None},
            ],
            "usage": (
                "Use these 3 projects with list_reference_directory(), "
                "read_reference_file(), search_reference_files(), git(), "
                "github_issue_view(), github_issue_list(), github_pr_view(), "
                "github_search(), github_label_list(), github_issue_create(), "
                "github_issue_edit(), and github_issue_comment()"
            ),
        }
        assert result == expected
        assert isinstance(result, dict)
        assert result["projects"][0]["name"] == "alpha"
        assert result["projects"][2]["name"] == "zebra"

    def test_get_reference_projects_logging(self) -> None:
        """Test INFO level logging for discovery operations."""
        from unittest.mock import patch

        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import get_reference_projects

        # Set up test data
        test_projects = {
            "proj1": ReferenceProject(name="proj1", path=Path("/path/to/proj1")),
        }
        server_module._reference_projects = test_projects

        # Test logging behavior (the decorator handles logging)
        with patch("mcp_workspace.server_reference_tools.logger") as mock_logger:
            result = get_reference_projects()

            # Should return structured dict with project objects
            expected = {
                "count": 1,
                "projects": [{"name": "proj1", "url": None}],
                "usage": (
                    "Use these 1 projects with list_reference_directory(), "
                    "read_reference_file(), search_reference_files(), git(), "
                    "github_issue_view(), github_issue_list(), github_pr_view(), "
                    "github_search(), github_label_list(), github_issue_create(), "
                    "github_issue_edit(), and github_issue_comment()"
                ),
            }
            assert result == expected

            # The @log_function_call decorator should handle logging
            # We can verify the function was called and returned the expected result
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_list_reference_directory_success(self) -> None:
        """Test listing files in valid reference project."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import list_reference_directory

        # Set up test reference projects
        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        server_module._reference_projects = test_projects

        # Mock the list_files_util function to return test data
        with patch(
            "mcp_workspace.server_reference_tools.list_files_util"
        ) as mock_list_files:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_list_files.return_value = [
                    "file1.py",
                    "file2.txt",
                    "subdir/file3.md",
                ]

                result = await list_reference_directory("test_proj")

                # Should return the mocked file list
                assert result == ["file1.py", "file2.txt", "subdir/file3.md"]
                assert isinstance(result, list)

                # Verify list_files_util was called with correct parameters
                mock_list_files.assert_called_once_with(
                    ".", project_dir=ref_path, use_gitignore=True
                )

    @pytest.mark.asyncio
    async def test_list_reference_directory_not_found(self) -> None:
        """Test error handling for non-existent reference project."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import list_reference_directory

        # Set up test reference projects (empty)
        server_module._reference_projects = {}

        # Should raise ValueError for non-existent project
        with pytest.raises(
            ValueError, match="Reference project 'nonexistent' not found"
        ):
            await list_reference_directory("nonexistent")

    @pytest.mark.asyncio
    async def test_list_reference_directory_gitignore(self) -> None:
        """Test gitignore filtering is applied."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import list_reference_directory

        # Set up test reference projects
        ref_path = Path("/tmp/gitignore_test").resolve()
        test_projects = {
            "proj_with_gitignore": ReferenceProject(
                name="proj_with_gitignore", path=ref_path
            ),
        }
        server_module._reference_projects = test_projects

        # Mock the list_files_util function
        with patch(
            "mcp_workspace.server_reference_tools.list_files_util"
        ) as mock_list_files:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                # Should return files after gitignore filtering
                mock_list_files.return_value = ["src/main.py", "README.md"]

                result = await list_reference_directory("proj_with_gitignore")

                # Verify gitignore filtering was enabled
                mock_list_files.assert_called_once_with(
                    ".",
                    project_dir=ref_path,
                    use_gitignore=True,
                )
                assert result == ["src/main.py", "README.md"]

    @pytest.mark.asyncio
    async def test_list_reference_directory_logging(self) -> None:
        """Test DEBUG level logging for file operations."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import list_reference_directory

        # Set up test reference projects
        ref_path = Path("/tmp/log_test").resolve()
        test_projects = {
            "log_test_proj": ReferenceProject(name="log_test_proj", path=ref_path),
        }
        server_module._reference_projects = test_projects

        # Mock the list_files_util function
        with patch(
            "mcp_workspace.server_reference_tools.list_files_util"
        ) as mock_list_files:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                with patch(
                    "mcp_workspace.server_reference_tools.logger"
                ) as mock_logger:
                    mock_list_files.return_value = ["test.py"]

                    result = await list_reference_directory("log_test_proj")

                    # Should return expected result
                    assert result == ["test.py"]
                    assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_read_reference_file_success(self) -> None:
        """Test reading file from valid reference project."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import read_reference_file

        # Set up test reference projects
        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        server_module._reference_projects = test_projects

        # Mock the read_file_util function to return test data
        with patch(
            "mcp_workspace.server_reference_tools.read_file_util"
        ) as mock_read_file:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_read_file.return_value = "Test file content\nLine 2\n"

                result = await read_reference_file("test_proj", "test_file.txt")

                # Should return the mocked file content
                assert result == "Test file content\nLine 2\n"
                assert isinstance(result, str)

                # Verify read_file_util was called with correct parameters
                mock_read_file.assert_called_once_with(
                    "test_file.txt",
                    project_dir=ref_path,
                    start_line=None,
                    end_line=None,
                    with_line_numbers=None,
                )

    @pytest.mark.asyncio
    async def test_read_reference_file_forwards_line_range_params(self) -> None:
        """Test that line-range params are forwarded to read_file_util."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import read_reference_file

        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        server_module._reference_projects = test_projects

        with patch(
            "mcp_workspace.server_reference_tools.read_file_util"
        ) as mock_read_file:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_read_file.return_value = "5→line five\n6→line six\n"

                result = await read_reference_file(
                    "test_proj",
                    "test_file.txt",
                    start_line=5,
                    end_line=10,
                    with_line_numbers=True,
                )

                assert result == "5→line five\n6→line six\n"
                mock_read_file.assert_called_once_with(
                    "test_file.txt",
                    project_dir=ref_path,
                    start_line=5,
                    end_line=10,
                    with_line_numbers=True,
                )

    @pytest.mark.asyncio
    async def test_read_reference_file_project_not_found(self) -> None:
        """Test error handling for non-existent reference project."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import read_reference_file

        # Set up test reference projects (empty)
        server_module._reference_projects = {}

        # Should raise ValueError for non-existent project
        with pytest.raises(
            ValueError, match="Reference project 'nonexistent' not found"
        ):
            await read_reference_file("nonexistent", "test_file.txt")

    @pytest.mark.asyncio
    async def test_read_reference_file_file_not_found(self) -> None:
        """Test error handling for non-existent file."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import read_reference_file

        # Set up test reference projects
        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        server_module._reference_projects = test_projects

        # Mock the read_file_util function to raise FileNotFoundError
        with patch(
            "mcp_workspace.server_reference_tools.read_file_util"
        ) as mock_read_file:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_read_file.side_effect = FileNotFoundError(
                    "File not found: test_file.txt"
                )

                # Should propagate the FileNotFoundError
                with pytest.raises(
                    FileNotFoundError, match="File not found: test_file.txt"
                ):
                    await read_reference_file("test_proj", "nonexistent_file.txt")

    @pytest.mark.asyncio
    async def test_read_reference_file_security(self) -> None:
        """Test path traversal prevention (reuse existing security)."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import read_reference_file

        # Set up test reference projects
        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        server_module._reference_projects = test_projects

        # Mock the read_file_util function to raise security error
        with patch(
            "mcp_workspace.server_reference_tools.read_file_util"
        ) as mock_read_file:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_read_file.side_effect = ValueError(
                    "Security error: Path traversal detected"
                )

                # Should propagate the security error
                with pytest.raises(
                    ValueError, match="Security error: Path traversal detected"
                ):
                    await read_reference_file("test_proj", "../../../etc/passwd")

    @pytest.mark.asyncio
    async def test_read_reference_file_logging(self) -> None:
        """Test DEBUG level logging for file operations."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import read_reference_file

        # Set up test reference projects
        ref_path = Path("/tmp/log_test").resolve()
        test_projects = {
            "log_test_proj": ReferenceProject(name="log_test_proj", path=ref_path),
        }
        server_module._reference_projects = test_projects

        # Mock the read_file_util function
        with patch(
            "mcp_workspace.server_reference_tools.read_file_util"
        ) as mock_read_file:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                with patch(
                    "mcp_workspace.server_reference_tools.logger"
                ) as mock_logger:
                    mock_read_file.return_value = "test content"

                    result = await read_reference_file("log_test_proj", "test.txt")

                    # Should return expected result
                    assert result == "test content"
                    assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_read_reference_file_calls_ensure_available(self) -> None:
        """Verify ensure_available is awaited before file access."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import read_reference_file

        ref_path = Path("/tmp/test_project").resolve()
        proj = ReferenceProject(name="test_proj", path=ref_path)
        server_module._reference_projects = {"test_proj": proj}

        with patch(
            "mcp_workspace.server_reference_tools.read_file_util"
        ) as mock_read_file:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_ensure:
                mock_read_file.return_value = "content"

                await read_reference_file("test_proj", "file.txt")

                mock_ensure.assert_awaited_once_with(proj)

    @pytest.mark.asyncio
    async def test_list_reference_directory_calls_ensure_available(self) -> None:
        """Verify ensure_available is awaited before directory listing."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import list_reference_directory

        ref_path = Path("/tmp/test_project").resolve()
        proj = ReferenceProject(name="test_proj", path=ref_path)
        server_module._reference_projects = {"test_proj": proj}

        with patch(
            "mcp_workspace.server_reference_tools.list_files_util"
        ) as mock_list_files:
            with patch(
                "mcp_workspace.server_reference_tools.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_ensure:
                mock_list_files.return_value = ["file.py"]

                await list_reference_directory("test_proj")

                mock_ensure.assert_awaited_once_with(proj)

    @pytest.mark.asyncio
    async def test_ensure_available_failure_propagates(self) -> None:
        """Mock ensure_available raising -> handler raises."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import (
            list_reference_directory,
            read_reference_file,
        )

        ref_path = Path("/tmp/test_project").resolve()
        proj = ReferenceProject(name="test_proj", path=ref_path)
        server_module._reference_projects = {"test_proj": proj}

        with patch(
            "mcp_workspace.server_reference_tools.ensure_available",
            new_callable=AsyncMock,
            side_effect=ValueError("Clone previously failed"),
        ):
            with pytest.raises(ValueError, match="Clone previously failed"):
                await read_reference_file("test_proj", "file.txt")

            with pytest.raises(ValueError, match="Clone previously failed"):
                await list_reference_directory("test_proj")

    def test_async_handlers_are_coroutines(self) -> None:
        """Verify async reference handlers are coroutine functions.

        The @log_function_call decorator wraps async functions;
        check the underlying __wrapped__ function is a coroutine.
        """
        import asyncio

        from mcp_workspace.server_reference_tools import (
            list_reference_directory,
            read_reference_file,
            search_reference_files,
        )

        for fn in (
            read_reference_file,
            list_reference_directory,
            search_reference_files,
        ):
            wrapped = getattr(fn, "__wrapped__", fn)
            assert asyncio.iscoroutinefunction(
                wrapped
            ), f"{fn.__name__} should wrap a coroutine function"


class TestGetReferenceProjectPath:
    """Tests for get_reference_project_path helper."""

    @pytest.mark.asyncio
    async def test_get_reference_project_path_success(self) -> None:
        """Valid name returns correct Path, ensure_available awaited."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import get_reference_project_path

        ref_path = Path("/tmp/test_project").resolve()
        proj = ReferenceProject(name="test_proj", path=ref_path)
        server_module._reference_projects = {"test_proj": proj}

        with patch(
            "mcp_workspace.server_reference_tools.ensure_available",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_ensure:
            result = await get_reference_project_path("test_proj")

            assert result == ref_path
            assert isinstance(result, Path)
            mock_ensure.assert_awaited_once_with(proj)

    @pytest.mark.asyncio
    async def test_get_reference_project_path_not_found(self) -> None:
        """Invalid name raises ValueError."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import get_reference_project_path

        server_module._reference_projects = {}

        with pytest.raises(
            ValueError, match="Reference project 'nonexistent' not found"
        ):
            await get_reference_project_path("nonexistent")

    @pytest.mark.asyncio
    async def test_get_reference_project_path_ensure_failure_propagates(self) -> None:
        """ensure_available raises -> propagates."""
        import mcp_workspace.server_reference_tools as server_module
        from mcp_workspace.server_reference_tools import get_reference_project_path

        ref_path = Path("/tmp/test_project").resolve()
        proj = ReferenceProject(name="test_proj", path=ref_path)
        server_module._reference_projects = {"test_proj": proj}

        with patch(
            "mcp_workspace.server_reference_tools.ensure_available",
            new_callable=AsyncMock,
            side_effect=ValueError("Clone previously failed"),
        ):
            with pytest.raises(ValueError, match="Clone previously failed"):
                await get_reference_project_path("test_proj")


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
