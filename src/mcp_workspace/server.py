"""MCP server exposing workspace file, search, git, and GitHub tools."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSpec

from mcp_workspace.checks.file_sizes import (
    check_file_sizes,
    load_allowlist,
    render_allowlisted,
    render_output,
)
from mcp_workspace.file_tools import DEFAULT_READ_MAX_LINES
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.toolset import tool_specs
from mcp_workspace.toolset._github_common import resolve_base_branch

# Initialize loggers
logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "This server provides file operations in one workspace directory. It "
    "also exposes reference projects: sibling codebases configured at "
    "startup, whose files are readable and searchable read-only. Most are "
    "local checkouts of GitHub repositories, so their history is available "
    "through git() and their GitHub issues and pull requests are reachable, "
    "with issues writable. Answer questions about another repo from its "
    "reference project instead of asking the user; call get_reference_projects() "
    "for the names, then pass one as reference_name."
)

F = TypeVar("F", bound=Callable[..., Any])

# Tools not yet moved into mcp_workspace.toolset; create_server adds them.
# Temporary: removed once the last group has moved.
_LEGACY_TOOLS: list[Callable[..., Any]] = []


def _legacy_tool(fn: F) -> F:
    """Mark fn as a legacy tool for create_server.

    Args:
        fn: The tool function.

    Returns:
        fn, unchanged.
    """
    _LEGACY_TOOLS.append(fn)
    return fn


# Store the project directory as a module-level variable
_project_dir: Path | None = None

# Per-project default line limit for check_file_size (set via --file-size-limit)
_file_size_limit: int | None = None

# Per-server default for check_branch_status' review gate (set via --fail-on-reviews)
_fail_on_reviews: bool = False


@log_function_call
def set_project_dir(directory: Path) -> None:
    """Set the project directory for file operations.

    Args:
        directory: The project directory path
    """
    global _project_dir  # pylint: disable=global-statement
    _project_dir = Path(directory)
    logger.info("Project directory set to: %s", _project_dir)


@log_function_call
def set_file_size_limit(limit: int | None) -> None:
    """Set the per-project default line limit used by check_file_size.

    Args:
        limit: Default line limit, or None to fall back to the built-in default.
    """
    global _file_size_limit  # pylint: disable=global-statement
    _file_size_limit = limit
    logger.info("File size limit set to: %s", limit)


@log_function_call
def set_fail_on_reviews(value: bool) -> None:
    """Set the per-server default for check_branch_status' review gate.

    Args:
        value: Default review-gate flag; the tool parameter overrides per call.
    """
    global _fail_on_reviews  # pylint: disable=global-statement
    _fail_on_reviews = value
    logger.info("Fail on reviews set to: %s", value)


@_legacy_tool
@log_function_call
def get_base_branch() -> str:
    """Detect the base branch for the current branch.

    Returns:
        Branch name string; "Error: issue #N: …" when the linked issue's Base
        Branch section is malformed (no fallback); "main" when nothing could be
        detected.

    Raises:
        ValueError: If the project directory has not been set.
    """
    # Lazy import: keeps PyGithub/GitPython off the server startup import path
    from mcp_workspace.git_operations.branch_queries import get_current_branch_name
    from mcp_workspace.github_operations.pr_manager import PullRequestManager

    if _project_dir is None:
        raise ValueError("Project directory has not been set")

    pr_manager: PullRequestManager | None = None

    try:
        pr_manager = PullRequestManager(_project_dir)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("GitHub manager initialization failed", exc_info=True)

    try:
        branch = get_current_branch_name(_project_dir)
        if branch is None:
            return "main"
        base, error = resolve_base_branch(_project_dir, branch, pr_manager)
        if error is not None:
            return error
        if base is None:
            return "main"
        return base
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("Base branch detection failed", exc_info=True)
        return "main"


@_legacy_tool
@log_function_call
def check_file_size(
    max_lines: int | None = None, show_allowlisted: bool = False
) -> str:
    """Check file line counts against threshold.

    Counts lines in every UTF-8 file under the project directory — all file
    types, tracked or not — excluding `.git/` and anything the project-root
    `.gitignore` matches. Nested `.gitignore` files are not read.

    Args:
        max_lines: Maximum allowed lines per file. When omitted, the default
            comes from the server's --file-size-limit flag, falling back to
            600 if that flag was not given.
        show_allowlisted: List only the `.large-files-allowlist` entries,
            each with its line count, `not scanned` or `missing`, largest
            first and uncapped; entries that can be removed are marked.
            This is a listing, never a failure — the gate is the call
            without this flag.

    Returns:
        Formatted report of files exceeding the threshold, or the
        allowlist listing when show_allowlisted is True.

    Raises:
        ValueError: If the project directory has not been set.
    """
    if _project_dir is None:
        raise ValueError("Project directory has not been set")
    effective = max_lines if max_lines is not None else _file_size_limit
    if effective is None:
        effective = 600
    allowlist_path = _project_dir / ".large-files-allowlist"
    allowlist = load_allowlist(allowlist_path)
    if show_allowlisted:
        return render_allowlisted(_project_dir, effective, allowlist)
    result = check_file_sizes(_project_dir, max_lines=effective, allowlist=allowlist)
    return render_output(result, effective)


@_legacy_tool
@log_function_call
async def check_branch_status(
    max_log_lines: int = 300,
    ci_timeout: int = 300,
    pr_timeout: int = 0,
    fail_on_reviews: bool | None = None,
) -> str:
    """Check comprehensive branch status: git state, CI, PR, tasks.

    Args:
        max_log_lines: Maximum CI log lines to include (default 300).
        ci_timeout: Seconds to poll for CI completion. 0 disables polling.
        pr_timeout: Seconds to poll for PR existence. 0 disables polling.
        fail_on_reviews: Enable the review-gate header. When omitted, uses the
            server's --fail-on-reviews default (off unless set).

    Returns:
        Formatted branch status report for LLM consumption.

    Raises:
        ValueError: If the project directory has not been set.
    """
    # Lazy import: keeps PyGithub/GitPython off the server startup import path
    from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

    if _project_dir is None:
        raise ValueError("Project directory has not been set")
    effective = fail_on_reviews if fail_on_reviews is not None else _fail_on_reviews
    return await async_poll_branch_status(
        _project_dir,
        max_log_lines=max_log_lines,
        ci_timeout=ci_timeout,
        pr_timeout=pr_timeout,
        fail_on_reviews=effective,
    )


class FastMCPSink:
    """ToolSink that registers each spec on a FastMCP server."""

    def __init__(self, mcp: FastMCP) -> None:
        self._mcp = mcp

    def add(self, spec: ToolSpec) -> None:
        """Register one spec under its name and description.

        Args:
            spec: The spec to register.
        """
        self._mcp.add_tool(spec.fn, name=spec.name, description=spec.description)


def _configure_legacy(project_dir: Path, settings: dict[str, Any]) -> None:
    """Apply the settings to the module globals the legacy tools read.

    Temporary: shrinks as tool groups move into mcp_workspace.toolset.

    Args:
        project_dir: Workspace root.
        settings: The keyword settings passed to create_server.
    """
    set_project_dir(project_dir)
    set_file_size_limit(settings.get("file_size_limit"))
    set_fail_on_reviews(settings.get("fail_on_reviews", False))


def create_server(project_dir: Path, **settings: Any) -> FastMCP:
    """Build a FastMCP server with every workspace tool registered.

    Args:
        project_dir: Workspace root the tools operate in.
        **settings: Keyword settings forwarded to tool_specs.

    Returns:
        A new FastMCP server.
    """
    mcp = FastMCP("File System Service", instructions=_INSTRUCTIONS)
    sink = FastMCPSink(mcp)
    for spec in tool_specs(project_dir, **settings):
        sink.add(spec)
    _configure_legacy(project_dir, settings)
    for fn in _LEGACY_TOOLS:
        mcp.add_tool(fn)
    return mcp


@log_function_call
def run_server(
    project_dir: Path,
    reference_projects: dict[str, ReferenceProject] | None = None,
    file_size_limit: int | None = None,
    fail_on_reviews: bool = False,
    enforce_base_branch_format: bool = True,
    read_max_lines: int | None = DEFAULT_READ_MAX_LINES,
) -> None:
    """Run the MCP server with the given project directory and optional reference projects.

    Args:
        project_dir: Path to the project directory
        reference_projects: Optional dictionary mapping project names to directory paths
        file_size_limit: Optional per-project default line limit for check_file_size
        fail_on_reviews: Per-server default for check_branch_status' review gate
        enforce_base_branch_format: Server-wide default for rejecting a malformed
            Base Branch section in github_issue_create / github_issue_edit
        read_max_lines: Full-read line limit for read_file and
            read_reference_file; None or 0 means no limit
    """
    logger.debug("Entering run_server function")

    mcp = create_server(
        project_dir,
        reference_projects=reference_projects,
        file_size_limit=file_size_limit,
        fail_on_reviews=fail_on_reviews,
        enforce_base_branch_format=enforce_base_branch_format,
        read_max_lines=read_max_lines,
    )

    # Run the server
    logger.info("Starting MCP server")
    logger.debug("About to call mcp.run()")
    mcp.run()
    logger.debug(
        "After mcp.run() call - this line will only execute if mcp.run() returns"
    )
