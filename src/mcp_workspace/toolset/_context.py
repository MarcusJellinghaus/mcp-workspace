"""Per-factory state shared by the tool closures of one tool_specs() call."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from mcp_workspace.file_tools.directory_utils import check_path_not_gitignored
from mcp_workspace.reference_projects import ReferenceProject


@dataclass(frozen=True)
class WorkspaceContext:
    """Per-factory state shared by the tool closures of one tool_specs() call.

    Attributes:
        project_dir: Workspace root every workspace tool operates in.
        reference_projects: Reference projects by name.
        read_max_lines: Full-read line limit for read tools; None or 0 means
            no limit.
        file_size_limit: Default line limit for check_file_size, or None for
            the built-in default.
        fail_on_reviews: Default for check_branch_status' review gate.
        enforce_base_branch_format: Whether a malformed Base Branch section
            is rejected by github_issue_create / github_issue_edit.
        file_locks: Per-file locks for concurrent edit safety.
    """

    project_dir: Path
    reference_projects: dict[str, ReferenceProject]
    read_max_lines: int | None
    file_size_limit: int | None
    fail_on_reviews: bool
    enforce_base_branch_format: bool
    file_locks: dict[str, asyncio.Lock] = field(default_factory=dict)


def check_not_gitignored(ctx: WorkspaceContext, file_path: str) -> None:
    """Raise ValueError if file_path is excluded by .gitignore (security boundary).

    Args:
        ctx: Context whose project_dir the path is relative to.
        file_path: Path to check, relative to the project directory.
    """
    check_path_not_gitignored(file_path, ctx.project_dir)
