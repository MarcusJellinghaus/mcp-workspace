"""MCP server exposing workspace file, search, git, and GitHub tools."""

import logging
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSpec

from mcp_workspace.file_tools import DEFAULT_READ_MAX_LINES
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.toolset import tool_specs

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

    logger.info(
        "Server settings: project_dir=%s, file_size_limit=%s, read_max_lines=%s, "
        "fail_on_reviews=%s, enforce_base_branch_format=%s",
        project_dir,
        file_size_limit,
        read_max_lines,
        fail_on_reviews,
        enforce_base_branch_format,
    )
    for project_name, project in (reference_projects or {}).items():
        logger.info("Reference project '%s' set to: %s", project_name, project.path)

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
