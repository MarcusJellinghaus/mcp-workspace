"""Tool group workspace.write: save_file, edit_file, append_file."""

import asyncio
import logging
from typing import Annotated

from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSink, tool_spec
from pydantic import Field

from mcp_workspace.file_tools import append_file as append_file_util
from mcp_workspace.file_tools import edit_file as edit_file_util
from mcp_workspace.file_tools import save_file as save_file_util
from mcp_workspace.toolset._context import WorkspaceContext, check_not_gitignored

logger = logging.getLogger(__name__)


def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.write tools bound to ctx.

    Args:
        sink: Receives one ToolSpec per tool.
        ctx: Settings and state the tools are bound to.
    """

    @log_function_call
    def save_file(
        file_path: Annotated[
            str,
            Field(
                description=(
                    "Path to the file to write to (relative to project directory)"
                )
            ),
        ],
        content: Annotated[str, Field(description="Content to write to the file")],
    ) -> bool:
        """Write a file, creating parent directories as needed.

        Auto-creates parent directories if they do not exist.

        Returns:
            True if the file was written successfully

        Raises:
            ValueError: If file_path is not a non-empty string or content is
                not a string.
        """
        if not file_path or not isinstance(file_path, str):
            logger.error("Invalid file path parameter: %s", file_path)
            raise ValueError(
                f"File path must be a non-empty string, got {type(file_path)}"
            )

        if content is None:  # defense-in-depth for direct callers
            logger.warning("Content is None, treating as empty string")  # type: ignore[unreachable]
            content = ""
        elif not isinstance(content, str):
            logger.error("Invalid content type: %s", type(content))  # type: ignore[unreachable]
            raise ValueError(f"Content must be a string, got {type(content)}")

        check_not_gitignored(ctx, file_path)

        logger.info("Writing to file: %s", file_path)
        try:
            success = save_file_util(file_path, content, project_dir=ctx.project_dir)
            return success
        except Exception as e:
            logger.error("Error writing to file: %s", str(e))
            raise

    @log_function_call
    def append_file(
        file_path: Annotated[
            str,
            Field(
                description=(
                    "Path to the file to append to (relative to project directory)"
                )
            ),
        ],
        content: Annotated[str, Field(description="Content to append to the file")],
    ) -> bool:
        """Append content to the end of a file.

        Returns:
            True if the content was appended successfully

        Raises:
            ValueError: If file_path is not a non-empty string or content is
                not a string.
        """
        if not file_path or not isinstance(file_path, str):
            logger.error("Invalid file path parameter: %s", file_path)
            raise ValueError(
                f"File path must be a non-empty string, got {type(file_path)}"
            )

        if content is None:  # defense-in-depth for direct callers
            logger.warning("Content is None, treating as empty string")  # type: ignore[unreachable]
            content = ""
        elif not isinstance(content, str):
            logger.error("Invalid content type: %s", type(content))  # type: ignore[unreachable]
            raise ValueError(f"Content must be a string, got {type(content)}")

        check_not_gitignored(ctx, file_path)

        logger.info("Appending to file: %s", file_path)
        try:
            success = append_file_util(file_path, content, project_dir=ctx.project_dir)
            return success
        except Exception as e:
            logger.error("Error appending to file: %s", str(e))
            raise

    @log_function_call
    async def edit_file(
        file_path: Annotated[
            str,
            Field(
                description="Path to the file to edit (relative to project directory)"
            ),
        ],
        old_string: Annotated[str, Field(description="Exact text to find and replace")],
        new_string: Annotated[str, Field(description="Replacement text")],
        replace_all: Annotated[
            bool,
            Field(
                description=(
                    "Replace all occurrences instead of requiring unique match"
                )
            ),
        ] = False,
    ) -> str:
        """Edit a file by exact string match; replace_all for multiple matches.

        Finds old_string in the file and replaces it with new_string.
        Empty old_string inserts new_string at the beginning of the file.
        Raises ValueError if old_string matches multiple locations
        (use replace_all=True to replace all).

        Line endings: an existing file keeps its style (mixed → most common,
        tie → platform default); a file with no line breaks follows
        .gitattributes eol=, else the platform default. Matching and the
        returned diff use LF.

        Returns:
            Git-style unified diff showing the changes, or a message
            if the edit was already applied.

        Raises:
            ValueError: If file_path is not a non-empty string.
        """
        if not file_path or not isinstance(file_path, str):
            raise ValueError(
                f"File path must be a non-empty string, got {type(file_path)}"
            )

        check_not_gitignored(ctx, file_path)

        abs_path = str((ctx.project_dir / file_path).resolve())
        lock = ctx.file_locks.setdefault(abs_path, asyncio.Lock())
        async with lock:
            return edit_file_util(
                file_path, old_string, new_string, replace_all, ctx.project_dir
            )

    for fn in (save_file, edit_file, append_file):
        sink.add(tool_spec(fn, group="workspace.write", read_only=False))
