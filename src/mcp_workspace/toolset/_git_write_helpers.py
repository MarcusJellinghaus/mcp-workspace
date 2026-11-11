"""Guardrails, orchestration and result formatting for the git write tools.

Imported lazily by ``toolset.git_write`` so GitPython stays off the server
startup import path; importing ``git_operations`` here at top level is fine.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from mcp_workspace.git_operations.branch_queries import (
    is_valid_branch_name_strict,
    resolve_base_ref,
    resolve_commit,
)
from mcp_workspace.git_operations.branches import (
    create_and_switch_branch,
    switch_branch,
)
from mcp_workspace.git_operations.core import GIT_SHORT_HASH_LENGTH, GitResult
from mcp_workspace.git_operations.rebase import operation_in_progress
from mcp_workspace.toolset._context import WorkspaceContext
from mcp_workspace.utils.url_credentials import scrub_credentials

logger = logging.getLogger(__name__)


def run_tool(fn: Callable[[], str]) -> str:
    """Run one tool body so that it never raises.

    Args:
        fn: The tool body.

    Returns:
        The body's result, or ``Error: <message>`` if it raised.
    """
    try:
        return fn()
    except Exception as e:  # pylint: disable=broad-exception-caught  # tool boundary: tools never raise
        logger.debug("git write tool failed", exc_info=True)
        return f"Error: {scrub_credentials(str(e))}"


def short(sha: str) -> str:
    """Return the abbreviated form of a commit SHA.

    Args:
        sha: Full commit SHA.

    Returns:
        The first seven characters of ``sha``.
    """
    return sha[:GIT_SHORT_HASH_LENGTH]


def failure(result: GitResult) -> str:
    """Render a failed GitResult as a tool error.

    Args:
        result: The failed result.

    Returns:
        ``Error: <reason>``, followed by git's stderr when there is any.
    """
    message = f"Error: {result['error']}"
    stderr = (result["stderr"] or "").strip()
    if stderr:
        message += f"\n{stderr}"
    return scrub_credentials(message)


def guard_operation(project_dir: Path) -> str | None:
    """Refuse to write while a rebase or merge is stopped mid-way.

    Args:
        project_dir: Repository to check.

    Returns:
        An error string, or None when no operation is in progress.
    """
    op = operation_in_progress(project_dir)
    if op is None:
        return None
    return f"Error: a {op} is in progress; finish or abort it first"


def guard_name(project_dir: Path, name: str, what: str) -> str | None:
    """Refuse a value that is not a literal, valid branch name.

    Args:
        project_dir: Repository whose git validates the name.
        name: Value to check.
        what: Parameter name used in the error message.

    Returns:
        An error string, or None when ``name`` is valid.
    """
    if is_valid_branch_name_strict(project_dir, name):
        return None
    return f"Error: invalid branch {what}: {name!r}"


def _git_branch(project_dir: Path, name: str, create: bool, base: str | None) -> str:
    """Body of the git_branch tool; see ``do_git_branch``.

    Returns:
        The tool result.
    """
    if base is not None and not create:
        return "Error: base requires create=True"
    error = guard_name(project_dir, name, "name")
    if error is None and base is not None:
        error = guard_name(project_dir, base, "base")
    if error is None:
        error = guard_operation(project_dir)
    if error:
        return error

    if not create:
        result = switch_branch(project_dir, name)
        return f"Switched to {name}" if result["success"] else failure(result)

    if resolve_base_ref(project_dir, f"origin/{name}"):
        return (
            f"Error: origin/{name} already exists; use git_branch(name, create=False)"
        )
    start = None
    if base is not None:
        start = resolve_base_ref(project_dir, base)
        if start is None:
            return f"Error: base {base!r} is not a local branch or origin/<branch>"
    result = create_and_switch_branch(
        project_dir,
        name,
        start,
        no_track=bool(start and start.startswith("refs/remotes/")),
    )
    if not result["success"]:
        return failure(result)
    sha = resolve_commit(project_dir, "HEAD")
    return f"Created {name} from {base or 'HEAD'}" + (f" ({short(sha)})" if sha else "")


def do_git_branch(
    ctx: WorkspaceContext, name: str, create: bool, base: str | None
) -> str:
    """Switch to a branch, or create one from HEAD or ``base``.

    Args:
        ctx: Context holding the workspace directory.
        name: Branch to switch to or create.
        create: Create ``name`` instead of switching to it.
        base: Local branch or ``origin/<branch>`` to create from; needs create.

    Returns:
        ``Switched to <name>``, ``Created <name> from <base|HEAD> (<sha7>)`` or
        ``Error: <reason>``.
    """
    return run_tool(lambda: _git_branch(ctx.project_dir, name, create, base))
