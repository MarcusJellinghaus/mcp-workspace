"""Tool group workspace.git: git."""

import asyncio
import logging
from typing import Annotated

from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSink, tool_spec
from pydantic import Field

from mcp_workspace.toolset._context import WorkspaceContext
from mcp_workspace.toolset.reference import reference_project_path

logger = logging.getLogger(__name__)


def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.git tool bound to ctx.

    Args:
        sink: Receives one ToolSpec per tool.
        ctx: Settings and state the tools are bound to.
    """

    @log_function_call
    async def git(
        command: Annotated[
            str,
            Field(
                description=(
                    "Git subcommand (log, diff, status, merge_base, fetch, "
                    "show, branch, rev_parse, ls_tree, ls_files, ls_remote, "
                    "check_ignore)."
                )
            ),
        ],
        args: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Optional CLI flags and operands. Flags are validated against "
                    "per-command security allowlists. Paths must be relative and "
                    "stay inside the repository. fetch and ls_remote take a "
                    "configured remote name only."
                )
            ),
        ] = None,
        pathspec: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Optional file paths appended after --, under the same path rule."
                )
            ),
        ] = None,
        search: Annotated[
            str | None,
            Field(
                description="Optional regex to filter output (log, diff, show only)."
            ),
        ] = None,
        context: Annotated[
            int,
            Field(description="Lines of context around search matches (default 3)."),
        ] = 3,
        max_lines: Annotated[
            int | None,
            Field(
                description=(
                    "Maximum output lines. Per-command defaults: log=50, diff=100, "
                    "status=200, others=100."
                )
            ),
        ] = None,
        compact: Annotated[
            bool,
            Field(
                description="If True, apply compact diff rendering (diff, show only)."
            ),
        ] = True,
        reference_name: Annotated[
            str | None,
            Field(
                description=(
                    "Optional reference project name. When set, runs git against "
                    "that project instead of the workspace."
                )
            ),
        ] = None,
    ) -> str:
        """Run a read-only git command on the workspace or a reference project.

        Returns:
            Command output, optionally filtered/truncated.
        """
        # Lazy import: keeps GitPython off the server startup import path
        from mcp_workspace.git_operations.read_operations import git as git_impl

        if reference_name is not None:
            project_dir = await reference_project_path(ctx, reference_name)
        else:
            project_dir = ctx.project_dir
        return await asyncio.to_thread(
            git_impl,
            command=command,
            project_dir=project_dir,
            args=args,
            pathspec=pathspec,
            search=search,
            context=context,
            max_lines=max_lines,
            compact=compact,
        )

    sink.add(tool_spec(git, group="workspace.git", read_only=True))
