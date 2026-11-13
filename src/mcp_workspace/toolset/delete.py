"""Tool group workspace.delete: delete_this_file, delete_directory."""

import logging
from typing import Annotated

from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSink, tool_spec
from pydantic import Field

from mcp_workspace.file_tools import delete_directory as delete_directory_util
from mcp_workspace.file_tools import delete_file as delete_file_util
from mcp_workspace.file_tools.directory_utils import check_tree_access
from mcp_workspace.toolset._context import WorkspaceContext, check_writable

logger = logging.getLogger(__name__)


def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.delete tools bound to ctx.

    Args:
        sink: Receives one ToolSpec per tool.
        ctx: Settings and state the tools are bound to.
    """

    @log_function_call
    def delete_this_file(
        file_path: Annotated[
            str,
            Field(
                description=(
                    "Path to the file to delete (relative to project directory)"
                )
            ),
        ],
    ) -> bool:
        """Delete a specified file from the filesystem.

        Handles files only, not directories — use delete_directory for directories.

        Returns:
            True if the file was deleted successfully

        Raises:
            ValueError: If file_path is not a non-empty string.
        """
        # delete_file does not work with Claude Desktop (!!!)  ;-)
        # Validate the file_path parameter
        if not file_path or not isinstance(file_path, str):
            logger.error("Invalid file path parameter: %s", file_path)
            raise ValueError(
                f"File path must be a non-empty string, got {type(file_path)}"
            )

        check_writable(ctx, file_path)

        logger.info("Deleting file: %s", file_path)
        try:
            # Directly delete the file without user confirmation
            success = delete_file_util(file_path, project_dir=ctx.project_dir)
            logger.info("File deleted successfully: %s", file_path)
            return success
        except Exception as e:
            logger.error("Error deleting file %s: %s", file_path, str(e))
            raise

    @log_function_call
    def delete_directory(
        dir_path: Annotated[
            str,
            Field(
                description=(
                    "Path to the directory to delete (relative to project directory)"
                )
            ),
        ],
        recursive: Annotated[
            bool,
            Field(description="Delete the directory and all its contents when True"),
        ] = False,
    ) -> list[str]:
        """Delete a directory (empty by default; recursive=True for non-empty).

        Handles directories only — for files use delete_this_file. Deletes an empty
        directory by default; pass recursive=True to delete a non-empty tree. Missing
        directory is a no-op (returns a message, no error).

        Returns:
            List of deleted paths (relative to project directory), or a single
            message when the directory does not exist.

        Raises:
            ValueError: If dir_path is not a non-empty string, the path is
                excluded by .gitignore, the path or any file in the tree
                (also inside ignored subdirectories) is read-only by
                .mcp-file-access, or the underlying deletion is rejected
                (outside project, project root, path-is-a-file, or non-empty
                without recursive).
        """
        if not dir_path or not isinstance(dir_path, str):
            logger.error("Invalid directory path parameter: %s", dir_path)
            raise ValueError(
                f"Directory path must be a non-empty string, got {type(dir_path)}"
            )

        check_writable(ctx, dir_path)
        check_tree_access(dir_path, None, ctx.project_dir)

        logger.info("Deleting directory: %s", dir_path)
        try:
            return delete_directory_util(
                dir_path, project_dir=ctx.project_dir, recursive=recursive
            )
        except Exception as e:
            logger.error("Error deleting directory %s: %s", dir_path, str(e))
            raise

    for fn in (delete_this_file, delete_directory):
        sink.add(tool_spec(fn, group="workspace.delete", read_only=False))
