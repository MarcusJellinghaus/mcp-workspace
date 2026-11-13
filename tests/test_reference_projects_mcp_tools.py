"""Tests for reference project MCP tools and search functionality."""

import logging
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mcp_workspace.file_tools import DEFAULT_READ_MAX_LINES
from mcp_workspace.file_tools.file_access import AccessListing
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.toolset._context import WorkspaceContext
from mcp_workspace.toolset.reference import (
    reference_project_path,
    reference_repo_url,
)
from tests.conftest import ToolMap


def _listing(*files: str) -> AccessListing:
    """Return a listing of files with a valid rules file and no notes."""
    return AccessListing(files=list(files), notes={}, problems=[])


class TestReferenceProjectMCPTools:
    """Test MCP tools functionality."""

    def test_get_reference_projects_empty(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test discovery tool returns empty dict when no projects."""
        tools = make_tools(reference_projects={})

        # Should return structured dict with empty projects list
        result = tools["get_reference_projects"]()
        expected = {
            "count": 0,
            "projects": [],
            "usage": "No reference projects available",
        }
        assert result == expected
        assert isinstance(result, dict)

    def test_get_reference_projects_sorted(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test discovery tool returns sorted list of project objects in structured dict."""
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
        tools = make_tools(reference_projects=test_projects)

        # Should return structured dict with sorted projects list of objects
        result = tools["get_reference_projects"]()
        expected = {
            "count": 3,
            "projects": [
                {"name": "alpha", "url": "https://github.com/org/alpha"},
                {"name": "beta", "url": None},
                {"name": "zebra", "url": None},
            ],
            "usage": (
                "Pass a name as reference_name to the reference file tools, git(), "
                "and the GitHub read tools; issues can also be created, edited and "
                "commented on"
            ),
        }
        assert result == expected
        assert isinstance(result, dict)
        assert result["projects"][0]["name"] == "alpha"
        assert result["projects"][2]["name"] == "zebra"

    def test_readme_usage_example_matches_source(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """README's quoted usage example stays byte-identical to the source literal."""
        tools = make_tools(
            reference_projects={
                "alpha": ReferenceProject(name="alpha", path=Path("/path/to/alpha")),
            }
        )
        usage = tools["get_reference_projects"]()["usage"]

        readme = Path(__file__).parent.parent / "README.md"
        assert f'"usage": "{usage}"' in readme.read_text(encoding="utf-8")

    def test_get_reference_projects_logging(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test INFO level logging for discovery operations."""
        # Set up test data
        test_projects = {
            "proj1": ReferenceProject(name="proj1", path=Path("/path/to/proj1")),
        }
        tools = make_tools(reference_projects=test_projects)

        with patch("mcp_workspace.toolset.reference.logger") as mock_logger:
            result = tools["get_reference_projects"]()

            # Should return structured dict with project objects
            expected = {
                "count": 1,
                "projects": [{"name": "proj1", "url": None}],
                "usage": (
                    "Pass a name as reference_name to the reference file tools, git(), "
                    "and the GitHub read tools; issues can also be created, edited and "
                    "commented on"
                ),
            }
            assert result == expected

            # Check the logged project count and names, not the message wording
            mock_logger.info.assert_called_once()
            assert mock_logger.info.call_args.args[1:] == (1, ["proj1"])

    @pytest.mark.asyncio
    async def test_list_reference_directory_success(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test listing files in valid reference project."""
        # Set up test reference projects
        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        tools = make_tools(reference_projects=test_projects)

        # Mock the listing walk to return test data
        with patch(
            "mcp_workspace.toolset.reference.list_accessible_files"
        ) as mock_list_files:
            with patch(
                "mcp_workspace.toolset.reference.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_list_files.return_value = _listing(
                    "file1.py", "file2.txt", "subdir/file3.md"
                )

                result = await tools["list_reference_directory"]("test_proj")

                # Should return the mocked file list
                assert result == ["file1.py", "file2.txt", "subdir/file3.md"]
                assert isinstance(result, list)

                # Verify the walk ran on the reference project root
                mock_list_files.assert_called_once_with(".", ref_path)

    @pytest.mark.asyncio
    async def test_list_reference_directory_not_found(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test error handling for non-existent reference project."""
        # Set up test reference projects (empty)
        tools = make_tools(reference_projects={})

        # Should raise ValueError for non-existent project
        with pytest.raises(
            ValueError, match="Reference project 'nonexistent' not found"
        ):
            await tools["list_reference_directory"]("nonexistent")

    @pytest.mark.asyncio
    async def test_list_reference_directory_gitignore(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test gitignore filtering is applied."""
        # Set up test reference projects
        ref_path = Path("/tmp/gitignore_test").resolve()
        test_projects = {
            "proj_with_gitignore": ReferenceProject(
                name="proj_with_gitignore", path=ref_path
            ),
        }
        tools = make_tools(reference_projects=test_projects)

        # Mock the listing walk
        with patch(
            "mcp_workspace.toolset.reference.list_accessible_files"
        ) as mock_list_files:
            with patch(
                "mcp_workspace.toolset.reference.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                # Should return files after gitignore filtering
                mock_list_files.return_value = _listing("src/main.py", "README.md")

                result = await tools["list_reference_directory"]("proj_with_gitignore")

                # Verify the filtering walk was used
                mock_list_files.assert_called_once_with(".", ref_path)
                assert result == ["src/main.py", "README.md"]

    @pytest.mark.asyncio
    async def test_list_reference_directory_logging(
        self, caplog: pytest.LogCaptureFixture, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test @log_function_call emits DEBUG logging for the tool."""
        # Set up test reference projects
        ref_path = Path("/tmp/log_test").resolve()
        test_projects = {
            "log_test_proj": ReferenceProject(name="log_test_proj", path=ref_path),
        }
        tools = make_tools(reference_projects=test_projects)

        # Mock the listing walk
        with patch(
            "mcp_workspace.toolset.reference.list_accessible_files"
        ) as mock_list_files:
            with patch(
                "mcp_workspace.toolset.reference.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_list_files.return_value = _listing("test.py")

                with caplog.at_level(
                    logging.DEBUG, logger="mcp_workspace.toolset.reference"
                ):
                    result = await tools["list_reference_directory"]("log_test_proj")

                # Should return expected result
                assert result == ["test.py"]

                # The decorator logs under the decorated function's module
                assert any(
                    record.name == "mcp_workspace.toolset.reference"
                    and record.levelno == logging.DEBUG
                    and "list_reference_directory" in record.getMessage()
                    for record in caplog.records
                )

    @pytest.mark.asyncio
    async def test_read_reference_file_success(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test reading file from valid reference project."""
        # Set up test reference projects
        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        tools = make_tools(reference_projects=test_projects)

        # Mock the read_file_util function to return test data
        with patch("mcp_workspace.toolset.reference.read_file_util") as mock_read_file:
            with patch(
                "mcp_workspace.toolset.reference.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_read_file.return_value = "Test file content\nLine 2\n"

                result = await tools["read_reference_file"](
                    "test_proj", "test_file.txt"
                )

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
                    max_lines=DEFAULT_READ_MAX_LINES,
                )

    @pytest.mark.asyncio
    async def test_read_reference_file_forwards_line_range_params(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test that line-range params are forwarded to read_file_util."""
        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        tools = make_tools(reference_projects=test_projects)

        with patch("mcp_workspace.toolset.reference.read_file_util") as mock_read_file:
            with patch(
                "mcp_workspace.toolset.reference.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_read_file.return_value = "5→line five\n6→line six\n"

                result = await tools["read_reference_file"](
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
                    max_lines=DEFAULT_READ_MAX_LINES,
                )

    @pytest.mark.asyncio
    async def test_read_reference_file_truncates_at_configured_limit(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        """A full read is cut at the configured read_max_lines."""
        ref = tmp_path / "ref"
        ref.mkdir()
        (ref / "five.txt").write_text(
            "l1\nl2\nl3\nl4\nl5\n", encoding="utf-8", newline="\n"
        )
        tools = make_tools(
            read_max_lines=3,
            reference_projects={
                "ref": ReferenceProject(name="ref", path=ref.resolve()),
            },
        )

        with patch(
            "mcp_workspace.toolset.reference.ensure_available",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await tools["read_reference_file"]("ref", "five.txt")

        assert result == (
            "l1\nl2\nl3\n"
            "[truncated: showing lines 1–3 of 5; continue with start_line=4, end_line=5]"
        )

    @pytest.mark.asyncio
    async def test_read_reference_file_project_not_found(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test error handling for non-existent reference project."""
        # Set up test reference projects (empty)
        tools = make_tools(reference_projects={})

        # Should raise ValueError for non-existent project
        with pytest.raises(
            ValueError, match="Reference project 'nonexistent' not found"
        ):
            await tools["read_reference_file"]("nonexistent", "test_file.txt")

    @pytest.mark.asyncio
    async def test_read_reference_file_file_not_found(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test error handling for non-existent file."""
        # Set up test reference projects
        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        tools = make_tools(reference_projects=test_projects)

        # Mock the read_file_util function to raise FileNotFoundError
        with patch("mcp_workspace.toolset.reference.read_file_util") as mock_read_file:
            with patch(
                "mcp_workspace.toolset.reference.ensure_available",
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
                    await tools["read_reference_file"](
                        "test_proj", "nonexistent_file.txt"
                    )

    @pytest.mark.asyncio
    async def test_read_reference_file_security(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test path traversal prevention (reuse existing security)."""
        # Set up test reference projects
        ref_path = Path("/tmp/test_project").resolve()
        test_projects = {
            "test_proj": ReferenceProject(name="test_proj", path=ref_path),
        }
        tools = make_tools(reference_projects=test_projects)

        # Mock the read_file_util function to raise security error
        with patch("mcp_workspace.toolset.reference.read_file_util") as mock_read_file:
            with patch(
                "mcp_workspace.toolset.reference.ensure_available",
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
                    await tools["read_reference_file"](
                        "test_proj", "../../../etc/passwd"
                    )

    @pytest.mark.asyncio
    async def test_read_reference_file_rejects_absolute_traversal(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        """An absolute path escaping the reference project is rejected.

        Unlike its neighbours, this test mocks neither read_file_util nor
        ensure_available: the real security check has to run, and
        ensure_available returns immediately because the directory exists.
        """
        ref = tmp_path / "ref"
        ref.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "credentials.env"
        secret.write_text("SECRET=1", encoding="utf-8")

        tools = make_tools(
            reference_projects={
                "ref": ReferenceProject(name="ref", path=ref.resolve()),
            }
        )

        escape = str(ref.resolve() / ".." / "outside" / "credentials.env")

        with pytest.raises(ValueError, match="Security error") as exc_info:
            await tools["read_reference_file"]("ref", escape)

        assert "SECRET=1" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_read_reference_file_logging(
        self, caplog: pytest.LogCaptureFixture, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Test @log_function_call emits DEBUG logging for the tool."""
        # Set up test reference projects
        ref_path = Path("/tmp/log_test").resolve()
        test_projects = {
            "log_test_proj": ReferenceProject(name="log_test_proj", path=ref_path),
        }
        tools = make_tools(reference_projects=test_projects)

        # Mock the read_file_util function
        with patch("mcp_workspace.toolset.reference.read_file_util") as mock_read_file:
            with patch(
                "mcp_workspace.toolset.reference.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ):
                mock_read_file.return_value = "test content"

                with caplog.at_level(
                    logging.DEBUG, logger="mcp_workspace.toolset.reference"
                ):
                    result = await tools["read_reference_file"](
                        "log_test_proj", "test.txt"
                    )

                # Should return expected result
                assert result == "test content"

                # The decorator logs under the decorated function's module
                assert any(
                    record.name == "mcp_workspace.toolset.reference"
                    and record.levelno == logging.DEBUG
                    and "read_reference_file" in record.getMessage()
                    for record in caplog.records
                )

    @pytest.mark.asyncio
    async def test_read_reference_file_calls_ensure_available(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Verify ensure_available is awaited before file access."""
        ref_path = Path("/tmp/test_project").resolve()
        proj = ReferenceProject(name="test_proj", path=ref_path)
        tools = make_tools(reference_projects={"test_proj": proj})

        with patch("mcp_workspace.toolset.reference.read_file_util") as mock_read_file:
            with patch(
                "mcp_workspace.toolset.reference.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_ensure:
                mock_read_file.return_value = "content"

                await tools["read_reference_file"]("test_proj", "file.txt")

                mock_ensure.assert_awaited_once_with(proj)

    @pytest.mark.asyncio
    async def test_list_reference_directory_calls_ensure_available(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Verify ensure_available is awaited before directory listing."""
        ref_path = Path("/tmp/test_project").resolve()
        proj = ReferenceProject(name="test_proj", path=ref_path)
        tools = make_tools(reference_projects={"test_proj": proj})

        with patch(
            "mcp_workspace.toolset.reference.list_accessible_files"
        ) as mock_list_files:
            with patch(
                "mcp_workspace.toolset.reference.ensure_available",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_ensure:
                mock_list_files.return_value = _listing("file.py")

                await tools["list_reference_directory"]("test_proj")

                mock_ensure.assert_awaited_once_with(proj)

    @pytest.mark.asyncio
    async def test_ensure_available_failure_propagates(
        self, make_tools: Callable[..., ToolMap]
    ) -> None:
        """Mock ensure_available raising -> handler raises."""
        ref_path = Path("/tmp/test_project").resolve()
        proj = ReferenceProject(name="test_proj", path=ref_path)
        tools = make_tools(reference_projects={"test_proj": proj})

        with patch(
            "mcp_workspace.toolset.reference.ensure_available",
            new_callable=AsyncMock,
            side_effect=ValueError("Clone previously failed"),
        ):
            with pytest.raises(ValueError, match="Clone previously failed"):
                await tools["read_reference_file"]("test_proj", "file.txt")

            with pytest.raises(ValueError, match="Clone previously failed"):
                await tools["list_reference_directory"]("test_proj")

    def test_async_handlers_are_coroutines(self, tools: ToolMap) -> None:
        """Verify async reference handlers are coroutine functions.

        The @log_function_call decorator wraps async functions;
        check the underlying __wrapped__ function is a coroutine.
        """
        import asyncio

        for name in (
            "read_reference_file",
            "list_reference_directory",
            "search_reference_files",
        ):
            fn = tools[name]
            wrapped = getattr(fn, "__wrapped__", fn)
            assert asyncio.iscoroutinefunction(wrapped), (
                f"{name} should wrap a coroutine function"
            )


def _context(projects: dict[str, ReferenceProject]) -> WorkspaceContext:
    """Return a WorkspaceContext holding projects, other settings at defaults."""
    return WorkspaceContext(
        project_dir=Path("/tmp/workspace").resolve(),
        reference_projects=projects,
        read_max_lines=DEFAULT_READ_MAX_LINES,
        file_size_limit=None,
        fail_on_reviews=False,
        enforce_base_branch_format=True,
    )


class TestReferenceRepoUrl:
    """Tests for toolset.reference.reference_repo_url."""

    def test_returns_configured_url(self) -> None:
        """A configured URL is returned and ensure_available is never called."""
        proj = ReferenceProject(
            name="p", path=Path("/tmp/p").resolve(), url="https://github.com/o/p"
        )

        with patch(
            "mcp_workspace.toolset.reference.ensure_available",
            new_callable=AsyncMock,
        ) as mock_ensure:
            result = reference_repo_url(_context({"p": proj}), "p")

        assert result == "https://github.com/o/p"
        mock_ensure.assert_not_called()

    def test_unknown_name(self) -> None:
        """An unknown name raises ValueError."""
        with pytest.raises(ValueError, match="Reference project 'nope' not found"):
            reference_repo_url(_context({}), "nope")

    def test_missing_url(self) -> None:
        """A project without a URL raises ValueError."""
        proj = ReferenceProject(name="p", path=Path("/tmp/p").resolve())

        with pytest.raises(
            ValueError, match="Reference project 'p' has no URL configured"
        ):
            reference_repo_url(_context({"p": proj}), "p")


class TestReferenceProjectPath:
    """Tests for reference_project_path helper."""

    @pytest.mark.asyncio
    async def test_reference_project_path_success(self) -> None:
        """Valid name returns correct Path, ensure_available awaited."""
        ref_path = Path("/tmp/test_project").resolve()
        proj = ReferenceProject(name="test_proj", path=ref_path)
        ctx = _context({"test_proj": proj})

        with patch(
            "mcp_workspace.toolset.reference.ensure_available",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_ensure:
            result = await reference_project_path(ctx, "test_proj")

            assert result == ref_path
            assert isinstance(result, Path)
            mock_ensure.assert_awaited_once_with(proj)

    @pytest.mark.asyncio
    async def test_reference_project_path_not_found(self) -> None:
        """Invalid name raises ValueError."""
        with pytest.raises(
            ValueError, match="Reference project 'nonexistent' not found"
        ):
            await reference_project_path(_context({}), "nonexistent")

    @pytest.mark.asyncio
    async def test_reference_project_path_ensure_failure_propagates(self) -> None:
        """ensure_available raises -> propagates."""
        ref_path = Path("/tmp/test_project").resolve()
        proj = ReferenceProject(name="test_proj", path=ref_path)
        ctx = _context({"test_proj": proj})

        with patch(
            "mcp_workspace.toolset.reference.ensure_available",
            new_callable=AsyncMock,
            side_effect=ValueError("Clone previously failed"),
        ):
            with pytest.raises(ValueError, match="Clone previously failed"):
                await reference_project_path(ctx, "test_proj")
