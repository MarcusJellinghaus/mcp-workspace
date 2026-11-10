"""Workspace tools exported as framework-neutral ToolSpecs."""

import dataclasses
import inspect
from collections.abc import Callable
from pathlib import Path

from mcp_coder_utils.tool_spec import ToolCollector, ToolSink, ToolSpec

from mcp_workspace.file_tools import DEFAULT_READ_MAX_LINES
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.toolset import delete, move, read, write
from mcp_workspace.toolset._context import WorkspaceContext

__all__ = ["tool_specs"]

# Each group's register(sink, ctx); groups are appended as they move here.
_GROUPS: tuple[Callable[[ToolSink, WorkspaceContext], None], ...] = (
    read.register,
    write.register,
    delete.register,
    move.register,
)


def tool_specs(
    project_dir: Path,
    *,
    reference_projects: dict[str, ReferenceProject] | None = None,
    read_max_lines: int | None = DEFAULT_READ_MAX_LINES,
    file_size_limit: int | None = None,
    fail_on_reviews: bool = False,
    enforce_base_branch_format: bool = True,
) -> tuple[ToolSpec, ...]:
    """Build the workspace tools bound to one project directory.

    Every call builds its own state, so two tool sets never share settings,
    references or file locks.

    Args:
        project_dir: Workspace root the tools operate in.
        reference_projects: Reference projects by name; none by default.
        read_max_lines: Full-read line limit for read_file and
            read_reference_file; None or 0 means no limit.
        file_size_limit: Default line limit for check_file_size, or None for
            the built-in default.
        fail_on_reviews: Default for check_branch_status' review gate.
        enforce_base_branch_format: Whether a malformed Base Branch section
            is rejected by github_issue_create / github_issue_edit.

    Returns:
        The tool specs, in registration order.
    """
    ctx = WorkspaceContext(
        project_dir=Path(project_dir),
        reference_projects=dict(reference_projects or {}),
        read_max_lines=read_max_lines,
        file_size_limit=file_size_limit,
        fail_on_reviews=fail_on_reviews,
        enforce_base_branch_format=enforce_base_branch_format,
    )
    collector = ToolCollector()
    for register in _GROUPS:
        register(collector, ctx)
    # Closure docstrings carry extra indentation on Python 3.11/3.12.
    return tuple(
        dataclasses.replace(spec, description=inspect.cleandoc(spec.description))
        for spec in collector
    )
