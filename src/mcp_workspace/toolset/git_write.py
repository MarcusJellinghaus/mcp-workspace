"""Tool group workspace.git: the guarded git write tools."""

import asyncio
import logging
from typing import Annotated

from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSink, tool_spec
from pydantic import Field

from mcp_workspace.toolset._context import WorkspaceContext

logger = logging.getLogger(__name__)


def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.git write tools bound to ctx.

    Args:
        sink: Receives one ToolSpec per tool.
        ctx: Settings and state the tools are bound to.
    """

    @log_function_call
    async def git_branch(
        name: Annotated[
            str,
            Field(description="Branch to switch to, or to create when create=True."),
        ],
        create: Annotated[
            bool,
            Field(
                description=(
                    "Create the branch (git checkout -b) instead of switching to "
                    "it. Refused when origin/<name> already exists."
                )
            ),
        ] = False,
        base: Annotated[
            str | None,
            Field(
                description=(
                    "Start point for create=True: a local branch or "
                    "origin/<branch> only (no SHAs, no tags). Defaults to HEAD. "
                    "A branch created from origin/<branch> gets no upstream."
                )
            ),
        ] = None,
    ) -> str:
        """Switch to a branch, or create one (modifies the repository).

        Without create, checks out the local branch `name`, or creates a local
        branch tracking origin/<name> when only that exists. Never fetches: a
        branch that exists only on GitHub needs a `git fetch` first. Refused
        while a rebase or merge is in progress.

        Returns:
            "Switched to <name>", "Created <name> from <base|HEAD> (<sha7>)",
            or "Error: <reason>".
        """
        # Lazy import: keeps GitPython off the server startup import path
        from mcp_workspace.toolset import _git_write_helpers as helpers

        async with ctx.git_write_lock:
            return await asyncio.to_thread(
                helpers.do_git_branch, ctx, name, create, base
            )

    @log_function_call
    async def git_branch_delete(
        name: Annotated[str, Field(description="Local branch to delete.")],
    ) -> str:
        """Force-delete a local branch whose tip is on GitHub (modifies the repository).

        Runs `git branch -D` only after proving the tip is on GitHub: origin's
        branch of that name contains it, origin/<default> contains it (local
        remote-tracking ref, no fetch), or a merged PR has it as head (needs a
        GitHub token; skipped without one). Refuses the current branch, the
        default branch (main and master when the default is unknown) and tips
        no check can find. Never deletes the remote branch.

        Returns:
            "Deleted branch <name> (tip <sha7> on origin)" plus a
            "Verified by: <check>" line, or "Error: <reason>".
        """
        # Lazy import: keeps GitPython off the server startup import path
        from mcp_workspace.toolset import _git_write_helpers as helpers

        async with ctx.git_write_lock:
            return await asyncio.to_thread(helpers.do_git_branch_delete, ctx, name)

    sink.add(tool_spec(git_branch, group="workspace.git", read_only=False))
    sink.add(tool_spec(git_branch_delete, group="workspace.git", read_only=False))
