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
from mcp_workspace.git_operations.commits import commit_paths, committed_files
from mcp_workspace.git_operations.core import (
    GIT_SHORT_HASH_LENGTH,
    CommitResult,
    GitResult,
)
from mcp_workspace.git_operations.rebase import operation_in_progress
from mcp_workspace.git_operations.remotes import (
    format_dirty_tree,
    push_current_branch,
    remote_head_sha,
)
from mcp_workspace.git_operations.staging import (
    list_untracked_paths,
    stage_paths,
    unstage_paths,
)
from mcp_workspace.git_operations.workflows import commit_all_changes
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
) -> tuple[str | None, bool, bool, list[str]]:
    """Check whether a branch tip is provably on GitHub.

    Tries, stopping at the first that passes: origin's ``<name>`` contains the
    tip; local ``origin/<default>`` contains it; a merged PR has it as head.

    Args:
        ctx: Context holding the workspace directory.
        name: Branch whose tip is checked.
        tip: Full SHA of the branch tip.
        default: Default branch name, or None when unknown.

    Returns:
        ``(passing check, object_missing, lookup_failed, notes)``: the
        description of the check that passed or None; whether some check could
        not decide because an object is missing locally; whether the
        ``ls-remote`` or merged-PR lookup failed (GitHub error, not a negative
        answer); reasons a check was skipped or failed.
    """
    project_dir = ctx.project_dir
    object_missing = False
    lookup_failed = False
    notes: list[str] = []

    remote = remote_head_sha(project_dir, name)
    if not remote["success"]:
        notes.append(f"GitHub branch check failed: {remote['error']}")
        lookup_failed = True
    elif remote["sha"]:
        contained = is_ancestor(project_dir, tip, remote["sha"])
        if contained:
            return f"{name} on GitHub contains the tip", object_missing, False, notes
        object_missing = object_missing or contained is None

    if default:
        contained = is_ancestor(project_dir, tip, f"refs/remotes/origin/{default}")
        if contained:
            return f"origin/{default} contains the tip", object_missing, False, notes
        object_missing = object_missing or contained is None

    try:
        manager = pr_manager(ctx, None)
    except Exception as e:  # pylint: disable=broad-exception-caught  # optional check: no token, no GitHub remote
        notes.append(f"merged-PR check skipped: {e}")
        return None, object_missing, lookup_failed, notes
    try:
        number = manager.find_merged_pr_by_head_sha(tip)
    except Exception as e:  # pylint: disable=broad-exception-caught  # GitHub error: auth, rate limit, 5xx, network
        notes.append(f"merged-PR check failed: {e}")
        return None, object_missing, True, notes
    if number is not None:
        return f"merged PR #{number}", object_missing, False, notes
    return None, object_missing, lookup_failed, notes


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

    check, object_missing, lookup_failed, notes = tip_on_github(ctx, name, tip, default)
    if check is None:
        if object_missing:
            message = (
                f"Error: cannot verify tip {short(tip)} of {name}: a commit is "
                "missing locally; run git fetch first"
            )
        elif lookup_failed:
            message = (
                f"Error: cannot verify tip {short(tip)} of {name}: the GitHub "
                "check failed; retry later"
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


_MAX_COMMITTED_FILES = 50


def format_commit_result(commit_hash: str, branch: str, files: list[str]) -> str:
    """Render a created commit with its file list.

    Args:
        commit_hash: Short SHA of the commit.
        branch: Branch the commit was made on.
        files: Paths changed by the commit.

    Returns:
        ``Committed <sha7> on <branch> (<n> files)`` followed by one indented
        line per file, capped at ``_MAX_COMMITTED_FILES``.
    """
    count = len(files)
    lines = [f"Committed {commit_hash} on {branch} ({count} file{'s' * (count != 1)})"]
    lines += [f"  {path}" for path in files[:_MAX_COMMITTED_FILES]]
    if count > _MAX_COMMITTED_FILES:
        lines.append(f"  ... showing {_MAX_COMMITTED_FILES} of {count} files")
    return "\n".join(lines)


def _commit_given_paths(
    project_dir: Path, message: str, paths: list[str]
) -> CommitResult | str:
    """Stage the untracked files under ``paths`` and commit exactly ``paths``.

    On failure the files staged here are unstaged again; they had no prior
    index state, so nothing the user staged is touched.

    Returns:
        The ``commit_paths`` result, or an error string when staging failed.
    """
    given = [Path(p) for p in paths]
    staged = [Path(p) for p in list_untracked_paths(given, project_dir)]
    staging = stage_paths(staged, project_dir)
    if not staging["success"]:
        # A failing chunk leaves earlier chunks staged
        unstage_paths(staged, project_dir)
        return failure(staging)

    result = commit_paths(message, given, project_dir)
    if not result["success"] and staged:
        unstage_paths(staged, project_dir)
    return result


def _render_commit(
    project_dir: Path, result: CommitResult, branch: str, paths: list[str] | None
) -> str:
    """Render a commit attempt of ``commit_paths`` or ``commit_all_changes``.

    Args:
        project_dir: Repository the commit ran in.
        result: The commit result.
        branch: Branch the commit was made on.
        paths: Paths given to ``commit_paths``; None for ``all=True``.

    Returns:
        The tool result; every outcome ends with the remaining changes.
    """
    if result["error_category"] == "nothing_to_commit":
        # Name the paths so a mistyped or missing one is visible
        given = f" for paths: {', '.join(paths)}" if paths else ""
        return f"Nothing to commit{given}" + format_dirty_tree(project_dir)
    if (result["success"] and result["commit_hash"] is None) or (
        result["error"] == "No staged files to commit"
    ):
        return "Nothing to commit" + format_dirty_tree(project_dir)
    if not result["success"]:
        # Shows what a failed all=True commit left staged
        return scrub_credentials(
            f"Error: {result['error']}" + format_dirty_tree(project_dir)
        )
    files = committed_files(project_dir)
    return format_commit_result(
        result["commit_hash"] or "HEAD", branch, files
    ) + format_dirty_tree(project_dir)


def _git_commit(
    project_dir: Path, message: str, paths: list[str] | None, commit_all: bool
) -> str:
    """Body of the git_commit tool; see ``do_git_commit``.

    Returns:
        The tool result.
    """
    if bool(paths) == commit_all:
        return "Error: pass exactly one of paths or all=True"
    if not message.strip():
        # Checked here: commit_all_changes would stage everything first
        return "Error: commit message is empty"
    error = guard_operation(project_dir)
    if error:
        return error
    branch = get_current_branch_name(project_dir)
    if branch is None:
        return "Error: HEAD is detached; switch to a branch first"

    result: CommitResult | str
    if commit_all:
        result = commit_all_changes(message, project_dir)
    else:
        result = _commit_given_paths(project_dir, message, paths or [])
    if isinstance(result, str):
        return result
    return _render_commit(project_dir, result, branch, paths)


def do_git_commit(
    ctx: WorkspaceContext, message: str, paths: list[str] | None, commit_all: bool
) -> str:
    """Commit exactly ``paths``, or every change with ``commit_all``.

    ``paths`` may name directories; untracked files under them are included.
    ``commit_all`` is ``git add -A`` plus a commit. Hooks run; no amend.

    Args:
        ctx: Context holding the workspace directory.
        message: Commit message.
        paths: Files or directories to commit; an empty list counts as none.
        commit_all: Commit every change instead of ``paths``.

    Returns:
        ``Committed <sha7> on <branch> (<n> files)`` with the file list and the
        remaining working-tree changes, ``Nothing to commit ...`` or
        ``Error: <reason>``.
    """
    return run_tool(lambda: _git_commit(ctx.project_dir, message, paths, commit_all))


def guard_push_branch(project_dir: Path) -> tuple[str | None, str | None]:
    """Find the branch to push, refusing a detached HEAD and the default branch.

    Args:
        project_dir: Repository to check.

    Returns:
        ``(branch, None)``, or ``(None, "Error: <reason>")``.
    """
    branch = get_current_branch_name(project_dir)
    if branch is None:
        return None, "Error: HEAD is detached; check out a branch first"
    default = get_default_branch_name(project_dir)
    if default is None:
        return None, (
            "Error: cannot determine the default branch (no origin/HEAD, no "
            "main/master); set it with git remote set-head origin -a"
        )
    if branch == default:
        return None, f"Error: refusing to push the default branch {branch}"
    return branch, None


def _git_push(project_dir: Path, force: bool) -> str:
    """Body of the git_push tools; see ``do_git_push``.

    Returns:
        The tool result.
    """
    branch, error = guard_push_branch(project_dir)
    if branch is None:
        return error or "Error: no branch to push"
    result = push_current_branch(project_dir, force)
    if not result["success"]:
        return failure(result)
    message = (
        f"Force-pushed {branch} to origin (lease ok)"
        if force
        else f"Pushed {branch} to origin"
    )
    output = (result["stderr"] or "").strip()
    if output:
        message += f"\n{output}"
    return scrub_credentials(message)


def do_git_push(ctx: WorkspaceContext, force: bool = False) -> str:
    """Push the current branch to origin with upstream tracking.

    Refuses a detached HEAD and the default branch. ``force`` pushes with
    ``--force-with-lease --force-if-includes``, never plain ``--force``.

    Args:
        ctx: Context holding the workspace directory.
        force: Force-push with lease instead of a fast-forward push.

    Returns:
        ``Pushed <branch> to origin`` (or ``Force-pushed <branch> to origin
        (lease ok)``) followed by git's push output, or ``Error: <reason>``.
    """
    return run_tool(lambda: _git_push(ctx.project_dir, force))
