"""Tool group workspace.reference: read-only access to reference projects."""

import logging
from pathlib import Path
from typing import Annotated, Any

from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSink, tool_spec
from pydantic import Field

from mcp_workspace.file_tools import list_files as list_files_util
from mcp_workspace.file_tools import read_file as read_file_util
from mcp_workspace.file_tools import search_files as search_files_util
from mcp_workspace.file_tools.directory_utils import FileAccess, require_access
from mcp_workspace.reference_projects import ensure_available
from mcp_workspace.toolset._context import WorkspaceContext
from mcp_workspace.utils.url_credentials import scrub_credentials

logger = logging.getLogger(__name__)


async def reference_project_path(ctx: WorkspaceContext, name: str) -> Path:
    """Resolve a reference project name to its local path, ensuring availability.

    Args:
        ctx: Context holding the configured reference projects.
        name: Reference project name.

    Returns:
        Local filesystem path of the reference project.

    Raises:
        ValueError: If no reference project with the given name exists.
    """
    if name not in ctx.reference_projects:
        raise ValueError(f"Reference project '{name}' not found")
    project = ctx.reference_projects[name]
    await ensure_available(project)
    return project.path


def reference_repo_url(ctx: WorkspaceContext, name: str) -> str:
    """Resolve a reference project name to its configured repository URL.

    Synchronous and side-effect free — unlike reference_project_path(),
    this never calls ensure_available(), so it never clones.

    Args:
        ctx: Context holding the configured reference projects.
        name: Reference project name.

    Returns:
        The configured repository URL.

    Raises:
        ValueError: If no reference project with the given name exists, or
            the project has no URL configured.
    """
    if name not in ctx.reference_projects:
        raise ValueError(f"Reference project '{name}' not found")
    url = ctx.reference_projects[name].url
    if url is None:
        raise ValueError(f"Reference project '{name}' has no URL configured")
    return url


def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.reference tools bound to ctx.

    Args:
        sink: Receives one ToolSpec per tool.
        ctx: Settings and state the tools are bound to.
    """

    @log_function_call
    def get_reference_projects() -> dict[str, Any]:
        """Get the available reference projects as {"name", "url"} entries.

        Returns:
            Dictionary containing:
            - count: Number of available projects
            - projects: List of {"name", "url"} dicts, sorted by name
            - usage: Which tools accept a returned name as reference_name

        Read the returned usage value for how to use the names.
        """
        try:
            # Return structured dict instead of simple list because MCP tool responses
            # can be ambiguous when displaying arrays - items may appear concatenated
            # or unclear to LLMs. This format ensures clear communication.

            if not ctx.reference_projects:
                logger.info("No reference projects configured")
                return {
                    "count": 0,
                    "projects": [],
                    "usage": "No reference projects available",
                }

            projects = sorted(
                [
                    {
                        "name": p.name,
                        "url": scrub_credentials(p.url) if p.url is not None else None,
                    }
                    for p in ctx.reference_projects.values()
                ],
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
                "usage": (
                    "Pass a name as reference_name to the reference file tools, git(), "
                    "and the GitHub read tools; issues can also be created, edited and "
                    "commented on"
                ),
            }

        except Exception as e:
            logger.error("Error getting reference projects: %s", str(e))
            raise

    @log_function_call
    async def read_reference_file(
        reference_name: Annotated[
            str, Field(description="Name of the reference project")
        ],
        file_path: Annotated[
            str,
            Field(
                description=(
                    "Path to the file to read (relative to reference project directory)"
                )
            ),
        ],
        start_line: Annotated[
            int | None,
            Field(
                description=(
                    "First line to return (1-based, inclusive). Requires end_line."
                )
            ),
        ] = None,
        end_line: Annotated[
            int | None,
            Field(
                description=(
                    "Last line to return (1-based, inclusive). Requires start_line."
                )
            ),
        ] = None,
        with_line_numbers: Annotated[
            bool | None,
            Field(
                description=(
                    "Prefix lines with line numbers. Defaults to True for "
                    "sliced reads, False for full reads."
                )
            ),
        ] = None,
    ) -> str:
        """Read a reference-project file, or a line slice via start_line/end_line.

        Returns:
            The contents of the file as a string. A full read beyond the
            configured limit (default 2000 lines) is cut, followed by a note
            giving the next start_line/end_line; an explicit range is returned
            in full.
        """
        ref_path = await reference_project_path(ctx, reference_name)

        require_access(file_path, ref_path, FileAccess.READ_ONLY)

        # Call read_file_util with the reference project directory
        # The utility function handles all parameter validation and security checks
        return read_file_util(
            file_path,
            project_dir=ref_path,
            start_line=start_line,
            end_line=end_line,
            with_line_numbers=with_line_numbers,
            max_lines=ctx.read_max_lines,
        )

    @log_function_call
    async def list_reference_directory(
        reference_name: Annotated[
            str, Field(description="Name of the reference project to list")
        ],
    ) -> list[str]:
        """List files and directories in a reference project directory.

        Returns:
            A list of filenames in the reference project directory. Paths are
            forward-slash separated on every platform and can be passed straight
            back to `read_reference_file`.
        """
        ref_path = await reference_project_path(ctx, reference_name)

        # Call list_files_util with gitignore filtering enabled
        # The utility function handles all parameter validation
        return list_files_util(".", project_dir=ref_path, use_gitignore=True)

    @log_function_call
    async def search_reference_files(
        reference_name: Annotated[
            str, Field(description="Name of the reference project")
        ],
        glob: Annotated[
            str | None,
            Field(
                description=(
                    "File path pattern with gitignore/wildmatch semantics — e.g. "
                    '"**/*.py", "tests/**/test_*.py", "/README.md" (root only). '
                    'Brace expansion is NOT supported: "{a,b}/f.py" matches a '
                    'literal "{a,b}" directory. Issue one call per alternative, '
                    'or widen to "*" and filter. A bare "*.py" is unanchored and '
                    "matches at any depth, unlike a shell glob. On Windows, "
                    "matching is case-insensitive by design, so a glob cannot "
                    "detect a filename casing mismatch — use `git ls-files`, "
                    "which reports the name as recorded in the index."
                )
            ),
        ] = None,
        pattern: Annotated[
            str | None,
            Field(
                description=(
                    "Python regex to match file contents. Invalid regex patterns "
                    "are automatically treated as literal text. "
                    '(e.g. "def foo", "TODO.*fix")'
                )
            ),
        ] = None,
        context_lines: Annotated[
            int,
            Field(
                description="Lines of context around each match (0 = match line only)"
            ),
        ] = 0,
        max_results: Annotated[
            int,
            Field(
                description="Maximum number of matches or files returned (default 50)"
            ),
        ] = 50,
        max_result_lines: Annotated[
            int, Field(description="Hard cap on total output lines (default 200)")
        ] = 200,
    ) -> dict[str, Any]:
        """Search file contents by regex and/or find files by glob pattern in a reference project.

        Modes:
            - File search: provide `glob` to find files by path pattern (like find)
            - Content search: provide `pattern` (regex) to search inside files (like grep)
            - Combined: both to search content within matching files

        Returns:
            Dict with matches (content search) or file list (file search),
            plus truncated flag if results were capped.
            Adds a "glob_note" key when the glob matched no files and contains
            "{", which wildmatch treats literally, distinguishing that from a
            genuine no-such-file result.
            A content search adds a "skipped_files" key listing project-relative
            paths that could not be read — a path rejected by the security check,
            or an unreadable file — present only when non-empty.
            Paths are forward-slash separated on every platform and can be
            passed straight back to `read_reference_file`.

        Raises:
            ValueError: If the glob matches nothing by construction (a gitignore
                comment, blank, negation-only, or unparseable pattern such as an
                unterminated "[").
        """
        ref_path = await reference_project_path(ctx, reference_name)

        return search_files_util(
            project_dir=ref_path,
            glob=glob,
            pattern=pattern,
            context_lines=context_lines,
            max_results=max_results,
            max_result_lines=max_result_lines,
        )

    for fn in (
        get_reference_projects,
        read_reference_file,
        list_reference_directory,
        search_reference_files,
    ):
        sink.add(tool_spec(fn, group="workspace.reference", read_only=True))
