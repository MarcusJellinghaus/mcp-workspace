"""Guardrails, orchestration and result formatting for the git write tools.

Imported lazily by ``toolset.git_write`` so GitPython stays off the server
startup import path; importing ``git_operations`` here at top level is fine.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from mcp_workspace.git_operations.branch_queries import (
    get_current_branch_name,
    get_default_branch_name,
    is_ancestor,
    is_valid_branch_name_strict,
    resolve_base_ref,
    resolve_commit,
)
from mcp_workspace.git_operations.branches import (
    create_and_switch_branch,
    delete_local_branch_force,
    switch_branch,
)
from mcp_workspace.git_operations.core import GIT_SHORT_HASH_LENGTH, GitResult
from mcp_workspace.git_operations.rebase import operation_in_progress
from mcp_workspace.git_operations.remotes import remote_head_sha
from mcp_workspace.toolset._context import WorkspaceContext
from mcp_workspace.toolset._github_common import pr_manager
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


def tip_on_github(
    ctx: WorkspaceContext, name: str, tip: str, default: str | None
) -> tuple[str | None, bool, list[str]]:
    """Check whether a branch tip is provably on GitHub.

    Tries, stopping at the first that passes: origin's ``<name>`` contains the
    tip; local ``origin/<default>`` contains it; a merged PR has it as head.

    Args:
        ctx: Context holding the workspace directory.
        name: Branch whose tip is checked.
        tip: Full SHA of the branch tip.
        default: Default branch name, or None when unknown.

    Returns:
        ``(passing check, object_missing, notes)``: the description of the
        check that passed or None; whether some check could not decide because
        an object is missing locally; reasons a check was skipped.
    """
    project_dir = ctx.project_dir
    object_missing = False
    notes: list[str] = []

    remote = remote_head_sha(project_dir, name)
    if not remote["success"]:
        notes.append(f"GitHub branch check failed: {remote['error']}")
    elif remote["sha"]:
        contained = is_ancestor(project_dir, tip, remote["sha"])
        if contained:
            return f"{name} on GitHub contains the tip", object_missing, notes
        object_missing = object_missing or contained is None

    if default:
        contained = is_ancestor(project_dir, tip, f"refs/remotes/origin/{default}")
        if contained:
            return f"origin/{default} contains the tip", object_missing, notes
        object_missing = object_missing or contained is None

    try:
        number = pr_manager(ctx, None).find_merged_pr_by_head_sha(tip)
    except Exception as e:  # pylint: disable=broad-exception-caught  # optional check: no token, auth, network
        notes.append(f"merged-PR check skipped: {e}")
        number = None
    if number is not None:
        return f"merged PR #{number}", object_missing, notes
    return None, object_missing, notes


def _git_branch_delete(ctx: WorkspaceContext, name: str) -> str:
    """Body of the git_branch_delete tool; see ``do_git_branch_delete``.

    Returns:
        The tool result.
    """
    project_dir = ctx.project_dir
    error = guard_name(project_dir, name, "name")
    if error:
        return error
    if name == get_current_branch_name(project_dir):
        return "Error: cannot delete the current branch"
    default = get_default_branch_name(project_dir)
    refused = {default} if default else {"main", "master"}
    if name in refused:
        return f"Error: refusing to delete the default branch {name}"
    tip = resolve_commit(project_dir, f"refs/heads/{name}")
    if tip is None:
        return f"Error: no local branch {name}"

    check, object_missing, notes = tip_on_github(ctx, name, tip, default)
    if check is None:
        if object_missing:
            message = (
                f"Error: cannot verify tip {short(tip)} of {name}: a commit is "
                "missing locally; run git fetch first"
            )
        else:
            message = (
                f"Error: refusing to delete {name}: tip {short(tip)} is not on GitHub"
            )
        return scrub_credentials("\n".join([message, *notes]))

    result = delete_local_branch_force(project_dir, name)
    if not result["success"]:
        return failure(result)
    return f"Deleted branch {name} (tip {short(tip)} on origin)\nVerified by: {check}"


def do_git_branch_delete(ctx: WorkspaceContext, name: str) -> str:
    """Force-delete a local branch whose tip is provably on GitHub.

    Refuses the current branch, the default branch (``main`` and ``master``
    when the default is unknown) and tips no check can find on GitHub. Never
    touches the remote branch.

    Args:
        ctx: Context holding the workspace directory.
        name: Local branch to delete.

    Returns:
        ``Deleted branch <name> (tip <sha7> on origin)`` plus a ``Verified by:``
        line, or ``Error: <reason>``.
    """
    return run_tool(lambda: _git_branch_delete(ctx, name))
