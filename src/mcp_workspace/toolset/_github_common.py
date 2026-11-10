"""GitHub helpers shared by the workspace.github tool modules."""

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp_workspace.toolset._context import WorkspaceContext
from mcp_workspace.toolset.reference import reference_repo_url

if TYPE_CHECKING:
    # Type-only: does not execute, so PyGithub stays off the startup import path
    from mcp_workspace.github_operations.issues import IssueManager
    from mcp_workspace.github_operations.pr_manager import PullRequestManager

logger = logging.getLogger(__name__)


def ref_suffix(reference_name: str | None) -> str:
    """Return the clause naming a reference project, or "" for the workspace.

    Args:
        reference_name: Reference project name, or None for the workspace.

    Returns:
        " in reference project '<name>'", or "" when no name is given — the
        empty string keeps every workspace-path message byte-identical.
    """
    return "" if reference_name is None else f" in reference project '{reference_name}'"


def issue_manager(ctx: WorkspaceContext, reference_name: str | None) -> "IssueManager":
    """Build an IssueManager for the workspace repo or a reference project.

    Args:
        ctx: Context holding the project directory and reference projects.
        reference_name: Optional reference project name. When None, the
            workspace repository is used.

    Returns:
        An IssueManager bound to the workspace repository when reference_name
        is None, otherwise to the reference project's repository URL.

    Raises:
        ValueError: If reference_name is not a configured reference project or
            that project has no URL configured, or if the manager cannot be
            constructed for the resolved repository.
    """  # noqa: DOC502 - propagated from reference_repo_url()/IssueManager
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.issues import IssueManager

    if reference_name is None:
        return IssueManager(project_dir=ctx.project_dir)
    return IssueManager(repo_url=reference_repo_url(ctx, reference_name))


def pr_manager(
    ctx: WorkspaceContext, reference_name: str | None
) -> "PullRequestManager":
    """Build a PullRequestManager for the workspace repo or a reference project.

    Args:
        ctx: Context holding the project directory and reference projects.
        reference_name: Optional reference project name. When None, the
            workspace repository is used.

    Returns:
        A PullRequestManager bound to the workspace repository when
        reference_name is None, otherwise to the reference project's
        repository URL.

    Raises:
        ValueError: If reference_name is not a configured reference project or
            that project has no URL configured, or if the manager cannot be
            constructed for the resolved repository.
    """  # noqa: DOC502 - propagated from reference_repo_url()/PullRequestManager
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.pr_manager import PullRequestManager

    if reference_name is None:
        return PullRequestManager(project_dir=ctx.project_dir)
    return PullRequestManager(repo_url=reference_repo_url(ctx, reference_name))


def linked_branches(
    ctx: WorkspaceContext, number: int, reference_name: str | None
) -> list[str] | None:
    """Look up an issue's linked branches; None when the lookup fails for any reason.

    Args:
        ctx: Context holding the project directory and reference projects.
        number: Issue number to look up.
        reference_name: Optional reference project name. When None, the
            workspace repository is used.

    Returns:
        Names of the branches linked to the issue, or None if the lookup failed.
    """
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.issues import IssueBranchManager

    try:
        if reference_name is None:
            manager = IssueBranchManager(project_dir=ctx.project_dir)
        else:
            manager = IssueBranchManager(
                repo_url=reference_repo_url(ctx, reference_name)
            )
        return manager.get_linked_branches_or_none(number)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("Linked branch lookup failed", exc_info=True)
        return None


def resolve_base_branch(
    project_dir: Path, branch: str, pr_manager: Any
) -> tuple[str | None, str | None]:
    """Resolve the base branch for ``branch`` from its issue, PR, merge-base or default.

    Args:
        project_dir: Path to the git repository.
        branch: Branch whose base is wanted.
        pr_manager: PullRequestManager for the PR lookup, or None to skip it.

    Returns:
        (base, None) — base may be None when detection found nothing — or
        (None, "Error: issue #N: <sentence>") when the issue's Base Branch section
        is malformed. Never falls back past a malformed section.
    """
    # pylint: disable=redefined-outer-name  # pr_manager: kept for the callers
    # Lazy imports: keep PyGithub/GitPython off the server startup import path
    from mcp_workspace.git_operations.base_branch import detect_base_branch
    from mcp_workspace.git_operations.branch_queries import (
        extract_issue_number_from_branch,
    )
    from mcp_workspace.github_operations import IssueIdentityMismatchError
    from mcp_workspace.github_operations.issues import IssueManager

    issue_data = None
    number = extract_issue_number_from_branch(branch)
    if number is not None:
        try:
            fetched = IssueManager(project_dir=project_dir).get_issue(number)
            issue_data = fetched if fetched.get("number", 0) > 0 else None
        except IssueIdentityMismatchError as e:
            # Must precede the broad catch: this is a ValueError subclass.
            logger.warning("%s", e)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Issue fetch for base branch failed", exc_info=True)

    if issue_data and issue_data.get("base_branch_error"):
        return None, f"Error: issue #{number}: {issue_data['base_branch_error']}"

    return (
        detect_base_branch(
            project_dir,
            current_branch=branch,
            issue_data=issue_data,
            pr_manager=pr_manager,
        ),
        None,
    )


def repo_access_error(manager: "IssueManager") -> str:
    """Build the error text for a repository that could not be accessed.

    Args:
        manager: Manager whose repository lookup came back empty.

    Returns:
        Error text naming the API base URL that was tried, so a non-GitHub or
        unreachable host is distinguishable from a missing repository.
    """
    identifier = manager.repo_identifier
    return f"Error: Could not access repository (tried {identifier.api_base_url})"


def repo_full_name(manager: "IssueManager") -> str | None:
    """Resolve the repository a manager reads from, for diagnostics.

    Args:
        manager: Manager to resolve the repository for.

    Returns:
        The "owner/repo" name, or None when the repository is not accessible.
    """
    repo = manager._get_repository()  # pylint: disable=protected-access
    return str(repo.full_name) if repo else None


def allowlist_for(associations: Iterable[str | None]) -> frozenset[str]:
    """Read the allowlist only when some author's role is not trusted.

    Args:
        associations: ``author_association`` of every author in the output.

    Returns:
        The login allowlist from `get_trusted_commenters`, or an empty set
        when every role is already trusted.
    """
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace import config
    from mcp_workspace.github_operations.trust import TRUSTED_ASSOCIATIONS

    if all(a in TRUSTED_ASSOCIATIONS for a in associations):
        return frozenset()
    # Looked up via the module so one test patch on mcp_workspace.config applies.
    return config.get_trusted_commenters()


def _rate_limit_message(exc: Exception) -> str | None:
    """Describe a rate-limit failure, or return None for any other error.

    Args:
        exc: The exception to describe.

    Returns:
        The message of a GitHubRateLimitError; otherwise
        format_rate_limit_error(exc).
    """
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations import format_rate_limit_error
    from mcp_workspace.github_operations.caching.errors import GitHubRateLimitError

    if isinstance(exc, GitHubRateLimitError):
        return exc.message
    return format_rate_limit_error(exc)


def api_error(exc: Exception, reference_name: str | None) -> str:
    """Render a GitHub or validation error as a caller-facing error string.

    Args:
        exc: The exception to render.
        reference_name: Reference project name, or None for the workspace.

    Returns:
        The rate-limit description for a rate limit; otherwise "Error: <message>"
        using GitHub's message when the exception carries a dict payload with
        one, otherwise str(exc).
    """
    if (msg := _rate_limit_message(exc)) is not None:
        return f"{msg}{ref_suffix(reference_name)}"
    # exc.data is not reliably a dict with a "message" key
    data = getattr(exc, "data", None)
    message = data.get("message") if isinstance(data, dict) else None
    return f"Error: {message or exc}{ref_suffix(reference_name)}"


def tool_error(e: Exception) -> str:
    """Render a tool failure as a user-facing error string.

    Args:
        e: The exception raised by the tool.

    Returns:
        The error string shown to the user; for rate limits it names the
        bucket and reset time.
    """
    return _rate_limit_message(e) or f"Error: {e}"
