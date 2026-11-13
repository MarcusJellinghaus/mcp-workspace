"""Tool group workspace.read: read_file, list_directory, search_files."""

import logging
from typing import Annotated, Any

from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSink, tool_spec
from pydantic import Field

from mcp_workspace.file_tools import list_directory_tree, normalize_path
from mcp_workspace.file_tools import read_file as read_file_util
from mcp_workspace.file_tools import search_files as search_files_util
from mcp_workspace.file_tools.access_rules import access_rules_warning
from mcp_workspace.file_tools.file_access import list_accessible_files
from mcp_workspace.toolset._context import WorkspaceContext, check_readable

logger = logging.getLogger(__name__)


def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.read tools bound to ctx.

    Args:
        sink: Receives one ToolSpec per tool.
        ctx: Settings and state the tools are bound to.
    """

    @log_function_call
    def search_files(
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
        """Search file contents by regex and/or find files by glob pattern.

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
            passed straight back to `read_file`.

        Raises:
            ValueError: If the glob matches nothing by construction (a gitignore
                comment, blank, negation-only, or unparseable pattern such as
                an unterminated "[").
        """  # noqa: DOC502 - propagates from search_files_util
        return search_files_util(
            project_dir=ctx.project_dir,
            glob=glob,
            pattern=pattern,
            context_lines=context_lines,
            max_results=max_results,
            max_result_lines=max_result_lines,
        )

    @log_function_call
    def list_directory(
        path: Annotated[
            str,
            Field(
                description=(
                    "Scope listing to a subtree (relative to project root). "
                    'Defaults to "." (entire project).'
                )
            ),
        ] = ".",
        dirs_only: Annotated[
            bool,
            Field(description='Show only directories, each with trailing "/".'),
        ] = False,
    ) -> list[str]:
        """List files and directories in the project directory.

        Returns:
            A list of path strings: files, directories (trailing ``/``),
            collapsed summaries (``dir/ (N files)``), or a truncation line
            when output exceeds the internal limit. Paths are forward-slash
            separated on every platform. A file line may end in
            `` (read-only)`` or `` (read-write, not committed)``; strip that
            suffix before passing the path to `read_file`. The first line may
            be a ``WARNING:`` about an invalid ``.mcp-file-access``.

        Raises:
            ValueError: If the path points to a file instead of a directory,
                or is excluded by .gitignore rules and not exposed by
                .mcp-file-access.
        """
        try:
            # Validate path — normalize_path handles traversal attacks
            abs_path, rel_path = normalize_path(path, ctx.project_dir)

            # A hidden file keeps the gitignore message
            if abs_path.is_file():
                check_readable(ctx, path)
                raise ValueError(
                    f"'{path}' is a file, not a directory. Use read_file() instead."
                )

            logger.info(
                "Listing files in project directory: %s (path=%s)",
                ctx.project_dir,
                path,
            )
            listing = list_accessible_files(path, ctx.project_dir)
            # The tree builder treats a suffix as part of the file name, so
            # collapsed and dirs_only lines stay unmarked
            entries = [
                f"{rel} {listing.notes[rel]}" if rel in listing.notes else rel
                for rel in listing.files
            ]
            lines = list_directory_tree(
                entries, base_path=rel_path, dirs_only=dirs_only
            )
            # Prepended after rendering, so outside the line cap
            warning = access_rules_warning(listing.problems)
            return [warning, *lines] if warning is not None else lines
        except Exception as e:
            logger.error("Error listing project directory: %s", str(e))
            raise

    @log_function_call
    def read_file(
        file_path: Annotated[
            str,
            Field(
                description="Path to the file to read (relative to project directory)"
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
        """Read a file, or a line slice via start_line/end_line.

        Returns:
            The contents of the file as a string. A full read beyond the
            configured limit (default 2000 lines) is cut, followed by a note
            giving the next start_line/end_line; an explicit range is returned
            in full.

        Raises:
            ValueError: If file_path is not a non-empty string.
        """
        if not file_path or not isinstance(file_path, str):
            logger.error("Invalid file path parameter: %s", file_path)
            raise ValueError(
                f"File path must be a non-empty string, got {type(file_path)}"
            )

        check_readable(ctx, file_path)

        logger.info("Reading file: %s", file_path)
        try:
            content = read_file_util(
                file_path,
                project_dir=ctx.project_dir,
                start_line=start_line,
                end_line=end_line,
                with_line_numbers=with_line_numbers,
                max_lines=ctx.read_max_lines,
            )
            return content
        except Exception as e:
            logger.error("Error reading file: %s", str(e))
            raise

    for fn in (read_file, list_directory, search_files):
        sink.add(tool_spec(fn, group="workspace.read", read_only=True))
