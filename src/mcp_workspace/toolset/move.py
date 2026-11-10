"""Tool group workspace.move: move_file."""

import logging
from typing import Annotated

from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSink, tool_spec
from pydantic import Field

from mcp_workspace.file_tools import move_file as move_file_util
from mcp_workspace.toolset._context import WorkspaceContext, check_not_gitignored

logger = logging.getLogger(__name__)


def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.move tool bound to ctx.

    Args:
        sink: Receives one ToolSpec per tool.
        ctx: Settings and state the tools are bound to.
    """

    @log_function_call
    def move_file(
        source_path: Annotated[
            str,
            Field(description="Source file/directory path (relative to project)"),
        ],
        destination_path: Annotated[
            str,
            Field(description="Destination path (relative to project)"),
        ],
    ) -> bool:
        """Move or rename a file or directory (git-aware, preserves history).

        Git-aware: uses `git mv` for tracked files (preserving rename/history);
        falls back to a plain filesystem move for untracked files or non-git repos.

        Returns:
            True if successful

        Raises:
            ValueError: If inputs are invalid
            FileNotFoundError: If source doesn't exist
            FileExistsError: If destination already exists
            PermissionError: If permission is denied
            RuntimeError: If the move operation fails for any other reason
        """
        # Validate inputs with simple error messages
        if not source_path or not isinstance(source_path, str):
            raise ValueError("Invalid source path")

        if not destination_path or not isinstance(destination_path, str):
            raise ValueError("Invalid destination path")

        check_not_gitignored(ctx, source_path)
        check_not_gitignored(ctx, destination_path)

        try:
            # Call the underlying function (all logic is handled internally)
            result = move_file_util(
                source_path, destination_path, project_dir=ctx.project_dir
            )

            # Return simple boolean
            return bool(result.get("success", False))

        except FileNotFoundError as exc:
            # Simplify error message for LLM
            raise FileNotFoundError("File not found") from exc
        except FileExistsError as exc:
            # Simplify error message for LLM
            raise FileExistsError("Destination already exists") from exc
        except PermissionError as exc:
            # Simplify error message for LLM
            raise PermissionError("Permission denied") from exc
        except ValueError as e:
            # For security errors, simplify the message
            if "Security" in str(e) or "outside" in str(e).lower():
                raise ValueError("Invalid path") from e
            raise ValueError("Invalid operation") from e
        except Exception as e:
            # Catch any other errors and simplify
            raise RuntimeError("Move operation failed") from e

    sink.add(tool_spec(move_file, group="workspace.move", read_only=False))
