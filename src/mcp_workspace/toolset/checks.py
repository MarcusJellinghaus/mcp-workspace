"""Tool group workspace.checks: check_file_size, check_branch_status, get_base_branch."""

import logging
from typing import Annotated

from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSink, tool_spec
from pydantic import Field

from mcp_workspace.checks.file_sizes import (
    check_file_sizes,
    load_allowlist,
    render_allowlisted,
    render_output,
)
from mcp_workspace.toolset._context import WorkspaceContext
from mcp_workspace.toolset._github_common import resolve_base_branch

logger = logging.getLogger(__name__)


def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.checks tools bound to ctx.

    Args:
        sink: Receives one ToolSpec per tool.
        ctx: Settings and state the tools are bound to.
    """

    @log_function_call
    def check_file_size(
        max_lines: Annotated[
            int | None,
            Field(
                description=(
                    "Maximum allowed lines per file. When omitted, the default "
                    "comes from the server's --file-size-limit flag, falling back "
                    "to 600 if that flag was not given."
                )
            ),
        ] = None,
        show_allowlisted: Annotated[
            bool,
            Field(
                description=(
                    "List only the `.large-files-allowlist` entries, each with "
                    "its line count, `not scanned` or `missing`, largest first "
                    "and uncapped; entries that can be removed are marked. This "
                    "is a listing, never a failure — the gate is the call "
                    "without this flag."
                )
            ),
        ] = False,
    ) -> str:
        """Check file line counts against threshold.

        Counts lines in every UTF-8 file under the project directory — all file
        types, tracked or not — excluding `.git/` and anything the gitignore
        rules (every `.gitignore` and `.git/info/exclude`) match.

        Returns:
            Formatted report of files exceeding the threshold, or the
            allowlist listing when show_allowlisted is True.
        """
        effective = max_lines if max_lines is not None else ctx.file_size_limit
        if effective is None:
            effective = 600
        allowlist = load_allowlist(ctx.project_dir / ".large-files-allowlist")
        if show_allowlisted:
            return render_allowlisted(ctx.project_dir, effective, allowlist)
        result = check_file_sizes(
            ctx.project_dir, max_lines=effective, allowlist=allowlist
        )
        return render_output(result, effective)

    @log_function_call
    async def check_branch_status(
        max_log_lines: Annotated[
            int,
            Field(description="Maximum CI log lines to include (default 300)."),
        ] = 300,
        ci_timeout: Annotated[
            int,
            Field(description="Seconds to poll for CI completion. 0 disables polling."),
        ] = 300,
        pr_timeout: Annotated[
            int,
            Field(description="Seconds to poll for PR existence. 0 disables polling."),
        ] = 0,
        fail_on_reviews: Annotated[
            bool | None,
            Field(
                description=(
                    "Enable the review-gate header. When omitted, uses the "
                    "server's --fail-on-reviews default (off unless set)."
                )
            ),
        ] = None,
    ) -> str:
        """Check comprehensive branch status: git state, CI, PR, tasks.

        Returns:
            Formatted branch status report for LLM consumption.
        """
        # Lazy import: keeps PyGithub/GitPython off the server startup import path
        from mcp_workspace.checks.branch_status_polling import (
            async_poll_branch_status,
        )

        effective = (
            fail_on_reviews if fail_on_reviews is not None else ctx.fail_on_reviews
        )
        return await async_poll_branch_status(
            ctx.project_dir,
            max_log_lines=max_log_lines,
            ci_timeout=ci_timeout,
            pr_timeout=pr_timeout,
            fail_on_reviews=effective,
        )

    @log_function_call
    def get_base_branch() -> str:
        """Detect the base branch for the current branch.

        Returns:
            Branch name string; "Error: issue #N: …" when the linked issue's Base
            Branch section is malformed (no fallback); "main" when nothing could be
            detected.
        """
        # Lazy import: keeps PyGithub/GitPython off the server startup import path
        from mcp_workspace.git_operations.branch_queries import (
            get_current_branch_name,
        )
        from mcp_workspace.github_operations.pr_manager import PullRequestManager

        pr_manager: PullRequestManager | None = None

        try:
            pr_manager = PullRequestManager(ctx.project_dir)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("GitHub manager initialization failed", exc_info=True)

        try:
            branch = get_current_branch_name(ctx.project_dir)
            if branch is None:
                return "main"
            base, error = resolve_base_branch(ctx.project_dir, branch, pr_manager)
            if error is not None:
                return error
            if base is None:
                return "main"
            return base
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Base branch detection failed", exc_info=True)
            return "main"

    for fn in (check_file_size, check_branch_status, get_base_branch):
        sink.add(tool_spec(fn, group="workspace.checks", read_only=True))
