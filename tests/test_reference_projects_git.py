"""Tests for git() with reference project support."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import ANY, AsyncMock, patch

import pytest
from git import Repo

from mcp_workspace.git_operations.origin_fetch import FetchOutcome
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.toolset._context import WorkspaceContext
from tests.conftest import ToolMap

_FETCH_TARGET = "mcp_workspace.git_operations.origin_fetch.fetch_origin"
_GIT_IMPL = "mcp_workspace.git_operations.read_operations.git"


def _ref_tools(
    make_tools: Callable[..., ToolMap], path: Path, interval: int = 15
) -> ToolMap:
    """Tools with one reference project ``ref`` at ``path``."""
    return make_tools(
        reference_projects={"ref": ReferenceProject(name="ref", path=path)},
        reference_fetch_interval_minutes=interval,
    )


class TestGitReferenceAutoFetch:
    """git(..., reference_name=...) fetches the reference project when stale."""

    @pytest.mark.git_integration
    @pytest.mark.asyncio
    async def test_log_origin_main_shows_upstream_commit(
        self, make_clone: Callable[[str], Path], make_tools: Callable[..., ToolMap]
    ) -> None:
        work = make_clone("work")
        up = make_clone("up")
        (up / "new.txt").write_text("new\n")
        repo = Repo(up)
        try:
            repo.index.add(["new.txt"])
            repo.index.commit("upstream change")
            repo.git.push("origin", "HEAD:refs/heads/main")
        finally:
            repo.close()

        tools = _ref_tools(make_tools, work)
        result = await tools["git"](
            command="log", args=["--oneline", "origin/main"], reference_name="ref"
        )

        assert "upstream change" in result
        assert "[reference" not in result

    @pytest.mark.asyncio
    async def test_fetch_failure_adds_trailing_note(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        tools = _ref_tools(make_tools, tmp_path)
        with (
            patch(_FETCH_TARGET, return_value=FetchOutcome(True, "boom")),
            patch(_GIT_IMPL, return_value="commit abc123"),
        ):
            result = await tools["git"](command="log", reference_name="ref")
        assert result == "commit abc123\n[reference ref: fetch failed (boom)]"

    @pytest.mark.asyncio
    async def test_fetch_failure_and_git_error(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        tools = _ref_tools(make_tools, tmp_path)
        with (
            patch(_FETCH_TARGET, return_value=FetchOutcome(True, "boom")),
            patch(_GIT_IMPL, side_effect=RuntimeError("fatal: bad revision")),
        ):
            with pytest.raises(ValueError) as exc_info:
                await tools["git"](command="log", reference_name="ref")
        assert str(exc_info.value) == (
            "fatal: bad revision\n[reference ref: fetch failed (boom)]"
        )
        assert exc_info.value.__context__ is None
        assert exc_info.value.__cause__ is None

    @pytest.mark.asyncio
    async def test_git_error_without_failure_is_unchanged(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        tools = _ref_tools(make_tools, tmp_path)
        error = RuntimeError("fatal: bad revision")
        with (
            patch(_FETCH_TARGET, return_value=FetchOutcome(True, None)),
            patch(_GIT_IMPL, side_effect=error),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                await tools["git"](command="log", reference_name="ref")
        assert exc_info.value is error

    @pytest.mark.asyncio
    async def test_interval_zero_does_not_fetch(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        tools = _ref_tools(make_tools, tmp_path, interval=0)
        with (
            patch(_FETCH_TARGET) as fetch,
            patch(_GIT_IMPL, return_value="out"),
        ):
            result = await tools["git"](command="log", reference_name="ref")
        fetch.assert_not_called()
        assert result == "out"

    @pytest.mark.asyncio
    async def test_workspace_call_does_not_fetch(self, tools: ToolMap) -> None:
        with (
            patch(_FETCH_TARGET) as fetch,
            patch(_GIT_IMPL, return_value="out"),
        ):
            assert await tools["git"](command="status") == "out"
        fetch.assert_not_called()


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
