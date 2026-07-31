"""MCP tool wrappers for reference project operations."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from mcp_coder_utils.log_utils import log_function_call

from mcp_workspace.file_tools import list_files as list_files_util
from mcp_workspace.file_tools import read_file as read_file_util
from mcp_workspace.file_tools import search_files as search_files_util
from mcp_workspace.reference_projects import ReferenceProject, ensure_available

logger = logging.getLogger(__name__)

_reference_projects: Dict[str, ReferenceProject] = {}


@log_function_call
def set_reference_projects(reference_projects: Dict[str, ReferenceProject]) -> None:
    """Set the reference projects for file operations.

    Args:
        reference_projects: Dictionary mapping project names to ReferenceProject instances
    """
    global _reference_projects  # pylint: disable=global-statement
    _reference_projects = (
        reference_projects.copy()
    )  # Create a copy to avoid external modifications

    # Log each reference project
    for project_name, project in reference_projects.items():
        logger.info("Reference project '%s' set to: %s", project_name, project.path)


@log_function_call
def get_reference_projects() -> Dict[str, Any]:
    """Get available reference project names.

    Returns:
        Dictionary containing:
        - count: Number of available projects
        - projects: List of project names
        - usage: Instructions for next steps

    Use the returned project names with list_reference_directory() and read_reference_file()
    """
    try:
        # Return structured dict instead of simple list because MCP tool responses
        # can be ambiguous when displaying arrays - items may appear concatenated
        # or unclear to LLMs. This format ensures clear communication.

        if not _reference_projects:
            logger.info("No reference projects configured")
            return {
                "count": 0,
                "projects": [],
                "usage": "No reference projects available",
            }

        projects = sorted(
            [{"name": p.name, "url": p.url} for p in _reference_projects.values()],
            key=lambda p: str(p["name"]),
        )
        logger.info(
            "Found %d reference projects: %s",
            len(projects),
            [p["name"] for p in projects],
        )

        return {
            "count": len(projects),
            "projects": projects,
            "usage": f"Use these {len(projects)} projects with list_reference_directory(), read_reference_file(), search_reference_files(), and git()",
        }

    except Exception as e:
        logger.error("Error getting reference projects: %s", str(e))
        raise


async def get_reference_project_path(name: str) -> Path:
    """Resolve a reference project name to its local path, ensuring availability.

    Returns:
        Local filesystem path of the reference project.

    Raises:
        ValueError: If no reference project with the given name exists.
    """
    if name not in _reference_projects:
        raise ValueError(f"Reference project '{name}' not found")
    project = _reference_projects[name]
    await ensure_available(project)
    return project.path


@log_function_call
async def read_reference_file(
    reference_name: str,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    with_line_numbers: Optional[bool] = None,
) -> str:
    """Read a reference-project file, or a line slice via start_line/end_line.

    Args:
        reference_name: Name of the reference project
        file_path: Path to the file to read (relative to reference project directory)
        start_line: First line to return (1-based, inclusive). Requires end_line.
        end_line: Last line to return (1-based, inclusive). Requires start_line.
        with_line_numbers: Prefix lines with line numbers. Defaults to True for
            sliced reads, False for full reads.

    Returns:
        The contents of the file as a string
    """
    ref_path = await get_reference_project_path(reference_name)

    # Call read_file_util with the reference project directory
    # The utility function handles all parameter validation and security checks
    return read_file_util(
        file_path,
        project_dir=ref_path,
        start_line=start_line,
        end_line=end_line,
        with_line_numbers=with_line_numbers,
    )


@log_function_call
async def list_reference_directory(reference_name: str) -> List[str]:
    """List files and directories in a reference project directory.

    Args:
        reference_name: Name of the reference project to list

    Returns:
        A list of filenames in the reference project directory
    """
    ref_path = await get_reference_project_path(reference_name)

    # Call list_files_util with gitignore filtering enabled
    # The utility function handles all parameter validation
    return list_files_util(".", project_dir=ref_path, use_gitignore=True)


@log_function_call
async def search_reference_files(
    reference_name: str,
    glob: Optional[str] = None,
    pattern: Optional[str] = None,
    context_lines: int = 0,
    max_results: int = 50,
    max_result_lines: int = 200,
) -> Dict[str, Any]:
    """Search file contents by regex and/or find files by glob pattern in a reference project.

    Modes:
        - File search: provide `glob` to find files by path pattern (like find)
        - Content search: provide `pattern` (regex) to search inside files (like grep)
        - Combined: both to search content within matching files

    Args:
        reference_name: Name of the reference project
        glob: File path pattern (e.g. "**/*.py", "tests/**/test_*.py")
        pattern: Python regex to match file contents. Invalid regex patterns are
            automatically treated as literal text. (e.g. "def foo", "TODO.*fix")
        context_lines: Lines of context around each match (0 = match line only)
        max_results: Maximum number of matches or files returned (default 50)
        max_result_lines: Hard cap on total output lines (default 200)

    Returns:
        Dict with matches (content search) or file list (file search),
        plus truncated flag if results were capped.
    """
    ref_path = await get_reference_project_path(reference_name)

    return search_files_util(
        project_dir=ref_path,
        glob=glob,
        pattern=pattern,
        context_lines=context_lines,
        max_results=max_results,
        max_result_lines=max_result_lines,
    )


def register(mcp: FastMCP) -> None:
    """Register reference project MCP tools on the given server."""
    mcp.tool()(get_reference_projects)
    mcp.tool()(read_reference_file)
    mcp.tool()(list_reference_directory)
    mcp.tool()(search_reference_files)
