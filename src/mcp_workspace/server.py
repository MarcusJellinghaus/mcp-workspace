"""MCP server exposing workspace file, search, git, and GitHub tools."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, cast

from mcp.server.fastmcp import FastMCP
from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSpec

from mcp_workspace.checks.file_sizes import (
    check_file_sizes,
    load_allowlist,
    render_allowlisted,
    render_output,
)
from mcp_workspace.file_tools import DEFAULT_READ_MAX_LINES, normalize_path
from mcp_workspace.file_tools.directory_utils import check_path_not_gitignored
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.server_reference_tools import (
    get_reference_repo_url,
    set_reference_projects,
)
from mcp_workspace.toolset import tool_specs
from mcp_workspace.toolset._github_common import (
    api_error,
    ref_suffix,
    repo_access_error,
    tool_error,
)

if TYPE_CHECKING:
    # Type-only: does not execute, so PyGithub stays off the startup import path
    from mcp_workspace.github_operations.issues import IssueManager
    from mcp_workspace.github_operations.pr_manager import PullRequestManager

# Initialize loggers
logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "This server provides file operations in one workspace directory. It "
    "also exposes reference projects: sibling codebases configured at "
    "startup, whose files are readable and searchable read-only. Most are "
    "local checkouts of GitHub repositories, so their history is available "
    "through git() and their GitHub issues and pull requests are reachable, "
    "with issues writable. Answer questions about another repo from its "
    "reference project instead of asking the user; call get_reference_projects() "
    "for the names, then pass one as reference_name."
)

F = TypeVar("F", bound=Callable[..., Any])

# Tools not yet moved into mcp_workspace.toolset; create_server adds them.
# Temporary: removed once the last group has moved.
_LEGACY_TOOLS: list[Callable[..., Any]] = []


def _legacy_tool(fn: F) -> F:
    """Mark fn as a legacy tool for create_server.

    Args:
        fn: The tool function.

    Returns:
        fn, unchanged.
    """
    _LEGACY_TOOLS.append(fn)
    return fn


# Store the project directory as a module-level variable
_project_dir: Path | None = None

# Per-project default line limit for check_file_size (set via --file-size-limit)
_file_size_limit: int | None = None

# Per-server default for check_branch_status' review gate (set via --fail-on-reviews)
_fail_on_reviews: bool = False

# Server-wide default for rejecting a malformed Base Branch section
# (set via --enforce-base-branch-format / --no-enforce-base-branch-format)
_enforce_base_branch_format: bool = True


def _check_labels(
    manager: Any,
    add: list[str],
    remove: list[str],
    reference_name: str | None = None,
) -> str | None:
    """Reject status-* labels on both sides, then unknown add-side names.

    Both checks are case-insensitive, because GitHub label names are: adding
    "Bug" attaches the existing "bug" rather than creating a second label, so an
    exact-match comparison would reject a valid name and — worse on the remove
    side, which has no known-label check — let "Status-04:..." past the guard.

    ``manager`` is typed ``Any`` rather than ``IssueManager`` on purpose: a real
    annotation would force a top-level ``github_operations`` import and pull
    PyGithub onto the server startup path.

    Args:
        manager: An IssueManager instance used to read the repository labels.
        add: Label names about to be added.
        remove: Label names about to be removed.
        reference_name: Reference project the labels belong to, or None for the
            workspace repository. Only used to compose the error messages; the
            labels themselves are read from ``manager``.

    Returns:
        An error string, or None when the labels are acceptable.

    Raises:
        Exception: Whatever ``get_available_labels`` raises. Deliberately not
            caught: a failed lookup must be reported as itself by the calling
            tool, never rendered as "unknown label(s)".
    """  # noqa: DOC502  # Exception propagates from get_available_labels
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.issues.status import is_status_label

    offenders = [n for n in (*add, *remove) if is_status_label(n)]
    if offenders:
        return (
            "Error: these tools do not modify status-* labels "
            f"({', '.join(offenders)}). Use github_issue_set_status"
        )
    if not add:
        return None
    # Not cached: the server can run for days, and a label created meanwhile
    # must not be wrongly rejected.
    known = {label["name"].casefold() for label in manager.get_available_labels()}
    unknown = [n for n in add if n.casefold() not in known]
    if unknown:
        # Suffix before the colon, so the label list stays terminal and a
        # multi-label message cannot read the project as another label.
        return (
            f"Error: unknown label(s){ref_suffix(reference_name)}: {', '.join(unknown)}"
        )
    return None


def _check_base_branch(body: str | None) -> str | None:
    """Reject a multi-line or invalid ref name ### Base Branch before any write.

    Args:
        body: Candidate issue body, or None when the caller is not changing
            the body (as in github_issue_edit).

    Returns:
        An error string naming the problem, the fix, and the section's first
        line (or invalid value), or None when the section is absent, empty,
        a single valid ref name, or the check is disabled.
    """
    if not _enforce_base_branch_format:
        return None
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.issues.base import (
        MalformedBaseBranchError,
        format_malformed_base_branch,
        parse_base_branch,
    )

    try:
        parse_base_branch(body or "")
    except MalformedBaseBranchError as exc:
        return f"Error: {format_malformed_base_branch(exc)}"
    return None


def _resolve_assignees(manager: Any, logins: list[str]) -> list[str]:
    """Resolve '@me' to the authenticated login, cached per GitHub host and token.

    Args:
        manager: An IssueManager instance used to read the authenticated user.
        logins: Requested assignee logins, possibly containing "@me".

    Returns:
        The logins with "@me" replaced by the authenticated username.
    """
    if "@me" not in logins:
        return list(logins)
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.base_manager import _cached_login

    # The manager's own host, so a reference project on a different GitHub host
    # resolves "@me" against that host rather than reusing another host's login.
    # Not get_authenticated_username(): that re-reads the token via
    # get_github_token() and would ignore a token passed to the manager.
    # pylint: disable=protected-access
    login = _cached_login(
        manager.github_token,
        manager.repo_identifier.api_base_url,
        manager._github_client,
    )
    return [login if name == "@me" else name for name in logins]


def _normalize_newlines(text: str | None) -> str:
    r"""Return text with CRLF and CR line endings folded to LF.

    Args:
        text: Text to normalize, or None for an absent body.

    Returns:
        The text with "\r\n" and "\r" replaced by "\n"; "" when text is None.
    """
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def _edit_change_lines(
    issue: Any,
    title: str | None,
    body: str | None,
    state: str | None,
    add_labels: list[str] | None,
    remove_labels: list[str] | None,
    assignees: list[str],
) -> list[str]:
    """Describe which requested changes are visible in the refetched issue.

    Only arguments the caller actually passed are reported: an argument left at
    None or [] is not a change and appears in neither list.

    Args:
        issue: Refetched IssueData to compare the request against.
        title: Requested title, or None when unchanged.
        body: Requested body, or None when unchanged.
        state: Requested state, or None when unchanged.
        add_labels: Label names requested to be added, if any.
        remove_labels: Label names requested to be removed, if any.
        assignees: Resolved logins requested to be assigned, if any.

    Returns:
        The "Applied:" and "Not applied:" lines, using "(none)" when empty.
    """
    # Casefolded because GitHub matches label names case-insensitively and
    # _check_labels accepts a differently-cased name: requesting "Bug" lands
    # the repository's "bug", which is applied, not "Not applied".
    labels = {name.casefold() for name in issue["labels"]}
    # Casefolded for the same reason: GitHub logins are case-insensitive and
    # the refetch returns the canonical casing.
    assigned = {name.casefold() for name in issue["assignees"]}
    checks = (
        # Stripped because edit_issue strips the title before writing it, just
        # as create_issue does; comparing against the raw request would report
        # a title edit that landed as "Not applied".
        ("title", title is not None, issue["title"] == (title or "").strip()),
        # Newline-normalized because GitHub may store CRLF as LF, which would
        # otherwise report a body edit that landed as "Not applied".
        (
            "body",
            body is not None,
            _normalize_newlines(issue["body"]) == _normalize_newlines(body),
        ),
        ("state", state is not None, issue["state"] == state),
        (
            "add_labels",
            bool(add_labels),
            all(n.casefold() in labels for n in add_labels or []),
        ),
        (
            "remove_labels",
            bool(remove_labels),
            all(n.casefold() not in labels for n in remove_labels or []),
        ),
        (
            "add_assignees",
            bool(assignees),
            all(a.casefold() in assigned for a in assignees),
        ),
    )
    applied = [name for name, requested, landed in checks if requested and landed]
    not_applied = [
        name for name, requested, landed in checks if requested and not landed
    ]
    return [
        f"Applied: {', '.join(applied) or '(none)'}",
        f"Not applied: {', '.join(not_applied) or '(none)'}",
    ]


def _check_not_gitignored(file_path: str) -> None:
    """Raise ValueError if path is excluded by .gitignore.

    This is a security boundary — always enforced, no toggle.

    Raises:
        ValueError: If the path is excluded by .gitignore.
    """  # noqa: DOC502 - propagates from check_path_not_gitignored
    if _project_dir is None:
        return  # Can't check without project_dir; other validation will catch this
    check_path_not_gitignored(file_path, _project_dir)


def _resolve_body(
    body: str | None, body_file: str | None, conflict: bool
) -> str | None:
    """Return the body to send: body unchanged, or body_file's text verbatim.

    The file is read under read_file's rules (gitignore boundary, project
    containment). A leading UTF-8 BOM is dropped; line endings are kept.

    Args:
        body: Inline body passed by the caller
        body_file: Project-relative path to read the body from, or None
        conflict: Whether body counts as passed alongside body_file

    Returns:
        body when body_file is None, otherwise the file's text.

    Raises:
        ValueError: conflict is True, the project directory is unset, the path is
            gitignored / outside the project / not a file, or the file is not UTF-8.
    """
    if body_file is None:
        return body
    if conflict:
        raise ValueError("pass either body or body_file, not both")
    if _project_dir is None:
        raise ValueError("Project directory has not been set")
    _check_not_gitignored(body_file)
    abs_path, _ = normalize_path(body_file, _project_dir)
    if not abs_path.is_file():
        raise ValueError(f"body_file '{body_file}' not found or not a file")
    try:
        # newline="" keeps CRLF; utf-8-sig drops a leading BOM
        with open(abs_path, encoding="utf-8-sig", newline="") as f:
            return f.read()
    except UnicodeDecodeError as e:
        raise ValueError(f"body_file '{body_file}' is not valid UTF-8") from e


@log_function_call
def set_project_dir(directory: Path) -> None:
    """Set the project directory for file operations.

    Args:
        directory: The project directory path
    """
    global _project_dir  # pylint: disable=global-statement
    _project_dir = Path(directory)
    logger.info("Project directory set to: %s", _project_dir)


@log_function_call
def set_file_size_limit(limit: int | None) -> None:
    """Set the per-project default line limit used by check_file_size.

    Args:
        limit: Default line limit, or None to fall back to the built-in default.
    """
    global _file_size_limit  # pylint: disable=global-statement
    _file_size_limit = limit
    logger.info("File size limit set to: %s", limit)


@log_function_call
def set_fail_on_reviews(value: bool) -> None:
    """Set the per-server default for check_branch_status' review gate.

    Args:
        value: Default review-gate flag; the tool parameter overrides per call.
    """
    global _fail_on_reviews  # pylint: disable=global-statement
    _fail_on_reviews = value
    logger.info("Fail on reviews set to: %s", value)


@log_function_call
def set_enforce_base_branch_format(value: bool) -> None:
    """Set the server-wide default for rejecting a malformed Base Branch section.

    Args:
        value: Whether a malformed `### Base Branch` section is rejected at
            write time in github_issue_create / github_issue_edit.
    """
    global _enforce_base_branch_format  # pylint: disable=global-statement
    _enforce_base_branch_format = value
    logger.info("Enforce base branch format set to: %s", value)


def _issue_manager(reference_name: str | None) -> "IssueManager":
    """Build an IssueManager for the workspace repo or a reference project.

    Args:
        reference_name: Optional reference project name. When None, the
            workspace repository is used.

    Returns:
        An IssueManager bound to the workspace repository when reference_name
        is None, otherwise to the reference project's repository URL.

    Raises:
        ValueError: If reference_name is not a configured reference project or
            that project has no URL configured, or if the manager cannot be
            constructed for the resolved repository.
    """  # noqa: DOC502 - propagated from get_reference_repo_url()/IssueManager
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.issues import IssueManager

    if reference_name is None:
        return IssueManager(project_dir=_project_dir)
    return IssueManager(repo_url=get_reference_repo_url(reference_name))


def _pr_manager(reference_name: str | None) -> "PullRequestManager":
    """Build a PullRequestManager for the workspace repo or a reference project.

    Args:
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
    """  # noqa: DOC502 - propagated from get_reference_repo_url()/PullRequestManager
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.pr_manager import PullRequestManager

    if reference_name is None:
        return PullRequestManager(project_dir=_project_dir)
    return PullRequestManager(repo_url=get_reference_repo_url(reference_name))


@_legacy_tool
@log_function_call
def github_issue_create(
    title: str,
    body: str = "",
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    reference_name: str | None = None,
    body_file: str | None = None,
) -> str:
    """Create a real GitHub issue. This writes to GitHub.

    Targets the workspace repository, or a reference project's repository when
    reference_name is given. Workflow status labels (status-*) are rejected —
    use `github_issue_set_status`. Other label names are validated against
    the target repository's labels before writing, so a typo cannot silently
    create a new label. A malformed `### Base Branch` section (more than one
    line) is rejected before any write, unless the server was started with
    `--no-enforce-base-branch-format`.

    Args:
        title: Issue title (required, cannot be empty)
        body: Issue description in Markdown (default: empty)
        labels: Label names to apply — each must already exist in the target
            repository
        assignees: GitHub usernames to assign; "@me" means the authenticated user
        reference_name: Optional reference project name. When set, the issue is
            created in that project's GitHub repository instead of the workspace
            repository.
        body_file: Optional project-relative path whose content is sent as the
            body, byte for byte (a leading UTF-8 BOM is dropped). Same path
            rules as read_file, so gitignored paths are refused. Mutually
            exclusive with a non-empty body. The title is never read from the
            file; the Base Branch check applies to the file text.

    Returns:
        "Created issue #<number> — <url>" followed by the resulting labels and
        assignees, or error message string.
    """
    try:
        body = cast(str, _resolve_body(body, body_file, conflict=bool(body)))
        body_error = _check_base_branch(body)
        if body_error:
            return body_error
        manager = _issue_manager(reference_name)
        label_error = _check_labels(manager, labels or [], [], reference_name)
        if label_error:
            return label_error
        resolved = _resolve_assignees(manager, assignees or [])
        issue = manager.create_issue(
            title=title,
            body=body,
            labels=labels,
            assignees=resolved or None,
        )
        # Empty IssueData is the library's swallowed-failure sentinel
        if not issue["number"]:
            return (
                "Error: issue creation failed - no issue was created"
                f"{ref_suffix(reference_name)}"
            )
        # GitHub drops a non-assignable login or an unusable label silently, so
        # the resulting lists are the only way a caller sees what did not take
        return (
            f"Created issue #{issue['number']} — {issue['url']}\n"
            f"Labels: {', '.join(issue['labels']) or '(none)'}\n"
            f"Assignees: {', '.join(issue['assignees']) or '(none)'}"
        )
    except Exception as e:
        return tool_error(e)


@_legacy_tool
@log_function_call
def github_issue_edit(
    number: int,
    title: str | None = None,
    body: str | None = None,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    add_assignees: list[str] | None = None,
    state: str | None = None,
    reference_name: str | None = None,
    body_file: str | None = None,
) -> str:
    """Modify a real GitHub issue. This writes to GitHub.

    Targets the workspace repository, or a reference project's repository when
    reference_name is given. Only the arguments you pass are changed. Label
    changes are additive and subtractive, never a replacement of the whole set.
    Workflow status labels (status-*) are rejected on the add and the remove
    side — use `github_issue_set_status`. When `body` or `body_file` is
    passed, a malformed `### Base Branch` section (more than one line) is
    rejected before any write, unless the server was started with
    `--no-enforce-base-branch-format`.

    The edit is not a transaction: if a later part fails, the earlier part
    stays applied. The result then opens with a warning naming which requested
    changes landed, followed by the resulting state. A failure that happens
    before any write instead opens with an error saying nothing was applied.

    Args:
        number: Issue number to edit (must be positive)
        title: New issue title; surrounding whitespace is stripped
        body: New issue description in Markdown
        add_labels: Label names to add — each must already exist in the target
            repository
        remove_labels: Label names to remove; labels already absent are ignored
        add_assignees: Usernames to assign; "@me" means the authenticated user
        state: New issue state — only "open" or "closed" are accepted
        reference_name: Optional reference project name. When set, the issue is
            edited in that project's GitHub repository instead of the workspace
            repository.
        body_file: Optional project-relative path whose content becomes the new
            body, byte for byte (a leading UTF-8 BOM is dropped). Same path
            rules as read_file, so gitignored paths are refused. Mutually
            exclusive with body — any body value, including "", conflicts.

    Returns:
        "Updated issue #<number> — <url> (state: <state>)" followed by the
        resulting labels and assignees. When nothing was applied, the same
        block opens with an error line and reads "Issue #<number> — ..."
        instead of "Updated issue". Or error message string.
    """
    # Lazy imports: keep PyGithub off the server startup import path
    from mcp_workspace.github_operations import (
        GithubException,
        RetryError,
        format_rate_limit_error,
    )
    from mcp_workspace.github_operations.issues.types import create_empty_issue_data

    try:
        # Pre-write validation. Nothing has been written yet, so a plain error
        # is honest — and it keeps the inner except below meaning exactly one
        # thing: the write sequence started and something after it failed.
        body = _resolve_body(body, body_file, conflict=body is not None)
        if number <= 0:
            return f"Error: invalid issue number: {number}"
        if title is not None and not title.strip():
            return "Error: Issue title cannot be empty"
        if state not in (None, "open", "closed"):
            return f"Error: state must be 'open' or 'closed', got: {state}"
        body_error = _check_base_branch(body)
        if body_error:
            return body_error

        manager = _issue_manager(reference_name)
        label_error = _check_labels(
            manager, add_labels or [], remove_labels or [], reference_name
        )
        if label_error:
            return label_error
        resolved = _resolve_assignees(manager, add_assignees or [])

        reason = ""
        # edit_issue appends one entry per write call it issues, before
        # issuing it. Empty therefore means no write was ever issued — the
        # failure came before the first one, or the request had no write to
        # make. Either way nothing can have been written, which is the only
        # case in which claiming "no changes were made" is honest.
        attempted: list[str] = []
        try:
            issue = manager.edit_issue(
                number,
                title=title,
                body=body,
                add_labels=add_labels,
                remove_labels=remove_labels,
                add_assignees=resolved or None,
                state=state,
                attempted_writes=attempted,
            )
            # Empty IssueData is the library's swallowed-failure sentinel
            if not issue["number"]:
                reason = "swallowed API error"
        except (GithubException, RetryError, ValueError) as exc:
            # _handle_github_errors re-raises 401/403, rate limits and every
            # ValueError, including the identity check on edit_issue's own
            # closing refetch. All can happen after part of the write landed.
            issue = create_empty_issue_data()
            reason = format_rate_limit_error(exc) or str(exc)

        if reason:
            # The write sequence may have started and did not finish cleanly —
            # read the issue back so the caller learns what actually landed.
            reread_error = ""
            try:
                issue = manager.get_issue(number)
            except Exception as exc:
                issue = create_empty_issue_data()
                reread_error = f": {format_rate_limit_error(exc) or exc}"
            if not issue["number"]:
                if not attempted:
                    return (
                        f"Error: issue #{number} not found or not accessible"
                        f"{ref_suffix(reference_name)} "
                        f"({reason}){reread_error} - no changes were made"
                    )
                return (
                    f"Error: edit of issue #{number} failed"
                    f"{ref_suffix(reference_name)} ({reason}) and the "
                    f"issue could not be re-read{reread_error} - these changes "
                    f"may or may not have been applied: {', '.join(attempted)}"
                )

        # Same signal as above: an empty write log means no write went out, so
        # nothing was applied — which makes both "partially failed" and
        # "Updated" untrue.
        failed_before_write = bool(reason) and not attempted
        lines: list[str] = []
        if failed_before_write:
            lines.append(
                f"Error: edit of issue #{number} failed ({reason}) "
                f"- no changes were made; current state below"
            )
        elif reason:
            lines.append(
                f"Warning: edit partially failed ({reason}) — resulting state below"
            )
            lines.extend(
                _edit_change_lines(
                    issue, title, body, state, add_labels, remove_labels, resolved
                )
            )
        state_verb = "Issue" if failed_before_write else "Updated issue"
        lines.append(
            f"{state_verb} #{issue['number']} — {issue['url']} "
            f"(state: {issue['state']})"
        )
        lines.append(f"Labels: {', '.join(issue['labels']) or '(none)'}")
        lines.append(f"Assignees: {', '.join(issue['assignees']) or '(none)'}")
        return "\n".join(lines)
    except Exception as e:
        return tool_error(e)


@_legacy_tool
@log_function_call
def github_issue_set_status(
    number: int,
    status: str,
    from_status: str | None = None,
    reference_name: str | None = None,
    refresh_labels: bool = False,
) -> str:
    """Set the workflow status label of a real GitHub issue. This writes to GitHub.

    Targets the workspace repository, or a reference project's repository when
    reference_name is given — no local clone is needed. ``status`` and
    ``from_status`` are full ``status-*`` label names that must already exist
    in the target repository, matched case-insensitively; list them with
    ``github_label_list(search="status-")``. Every other ``status-*`` label on
    the issue is removed; other labels are kept. Pull requests are rejected;
    closed issues are allowed. A status change can start workflow automation
    in the target repository.

    Valid status labels come from a disk cache shared across sessions, kept for
    up to 24 h; pass ``refresh_labels=True`` to reload it when a newly created
    label is reported as not found.

    Args:
        number: Issue number.
        status: Target status label, e.g. "status-01:created".
        from_status: Optional guard. When set, the status is changed only if
            the issue's sole current status label is this one; otherwise
            nothing is written.
        reference_name: Optional reference project name. When set, the issue is
            changed in that project's GitHub repository instead of the
            workspace repository.
        refresh_labels: Force a reload of the label cache from GitHub.

    Returns:
        The old and new status with the resulting labels, a no-op or guard
        message, the available status labels when a label is not found, or
        error message string.
    """
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.issues.status import set_issue_status

    try:
        return set_issue_status(
            _issue_manager(reference_name),
            number,
            status,
            from_status,
            refresh_labels,
        )
    except Exception as e:
        return tool_error(e)


def _subissue_write(
    parent_number: int,
    child_number: int,
    unlink: bool,
    reference_name: str | None,
) -> str:
    """Link or unlink a sub-issue and render the outcome.

    Args:
        parent_number: Parent issue number.
        child_number: Child issue number.
        unlink: Remove the link when True, add it when False.
        reference_name: Reference project name, or None for the workspace.

    Returns:
        The success line, or error message string.
    """
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations import GithubException, RetryError

    suffix = ref_suffix(reference_name)
    for number in (parent_number, child_number):
        if number <= 0:
            return f"Error: invalid issue number: {number}{suffix}"
    if parent_number == child_number:
        return f"Error: an issue cannot be its own sub-issue{suffix}"
    try:
        manager = _issue_manager(reference_name)
    except ValueError as exc:
        # No suffix: the message already names the reference project
        return f"Error: {exc}"
    try:
        call = manager.remove_sub_issue if unlink else manager.add_sub_issue
        link = call(parent_number, child_number)
        if link is None:
            return repo_access_error(manager)
        # GitHub's sub_issues_summary lags after a write, even on the refetch;
        # counting via the list endpoint was rejected for its API cost.
        count = "" if link.total is None else f" (~{link.total} sub-issues, may lag)"
        verb = "Unlinked" if unlink else "Linked"
        relation = "from" if unlink else "as a sub-issue of"
        return f"{verb} #{child_number} {relation} #{parent_number} — {link.url}{count}"
    except (GithubException, RetryError, ValueError) as exc:
        return api_error(exc, reference_name)


@_legacy_tool
@log_function_call
def github_subissue_add(
    parent_number: int, child_number: int, reference_name: str | None = None
) -> str:
    """Link an existing issue as a sub-issue of another. This writes to GitHub.

    Both issues live in the same repository: the workspace repository, or the
    reference project's repository when reference_name is given — it scopes
    both numbers. GitHub rejects a child that already has a parent, here or
    elsewhere, with one generic message; call github_subissue_list first if
    the difference matters.

    Args:
        parent_number: Parent issue number (must be positive)
        child_number: Issue number to link under the parent (must be positive
            and differ from parent_number)
        reference_name: Optional reference project name. When set, both issues
            are in that project's GitHub repository instead of the workspace
            repository.

    Returns:
        "Linked #<child> as a sub-issue of #<parent> — <url> (~<N> sub-issues,
        may lag)", or error message string. The count is approximate and
        omitted when it could not be read. Call github_subissue_list for the
        exact set.
    """
    return _subissue_write(parent_number, child_number, False, reference_name)


@_legacy_tool
@log_function_call
def github_subissue_remove(
    parent_number: int, child_number: int, reference_name: str | None = None
) -> str:
    """Unlink a sub-issue from its parent. This writes to GitHub.

    Both issues live in the same repository: the workspace repository, or the
    reference project's repository when reference_name is given — it scopes
    both numbers. Removing a child that is not linked to the parent is an
    error, not a silent no-op.

    Args:
        parent_number: Parent issue number (must be positive)
        child_number: Issue number to unlink from the parent (must be positive
            and differ from parent_number)
        reference_name: Optional reference project name. When set, both issues
            are in that project's GitHub repository instead of the workspace
            repository.

    Returns:
        "Unlinked #<child> from #<parent> — <url> (~<N> sub-issues, may lag)",
        or error message string. The count is approximate and omitted when it
        could not be read. Call github_subissue_list for the exact set.
    """
    return _subissue_write(parent_number, child_number, True, reference_name)


@_legacy_tool
@log_function_call
def github_issue_comment(
    number: int,
    body: str = "",
    reference_name: str | None = None,
    body_file: str | None = None,
) -> str:
    """Post a real comment on a GitHub issue. This writes to GitHub.

    Pass the comment text as `body` or `body_file` — exactly one. Multi-line
    Markdown is sent through unchanged, except that leading and trailing
    whitespace is stripped.

    Args:
        number: Issue number to comment on (must be positive)
        body: Comment text in Markdown (cannot be empty when body_file is not
            given)
        reference_name: Optional reference project name. When set, the comment is
            posted to that project's GitHub repository instead of the workspace
            repository.
        body_file: Optional project-relative path whose content becomes the
            comment text (a leading UTF-8 BOM is dropped). Same path rules as
            read_file, so gitignored paths are refused. Mutually exclusive with
            a non-empty body.

    Returns:
        "Added comment to issue #<number> — <url>", or error message string.
    """
    try:
        body = cast(str, _resolve_body(body, body_file, conflict=bool(body)))
        if not body:
            if body_file is not None:
                return f"Error: body_file '{body_file}' is empty"
            return "Error: pass body or body_file"
        manager = _issue_manager(reference_name)
        comment = manager.add_comment(number, body)
        # Empty CommentData carries id == 0, not number == 0 as issues do
        if not comment["id"]:
            return (
                f"Error: failed to add comment to issue #{number}"
                f"{ref_suffix(reference_name)}"
            )
        return f"Added comment to issue #{number} — {comment['url']}"
    except Exception as e:
        return tool_error(e)


@_legacy_tool
@log_function_call
def github_review_comment_reply(
    pr_number: int,
    comment_id: int,
    body: str,
    reference_name: str | None = None,
) -> str:
    """Reply to an inline PR review comment. This writes to GitHub.

    Args:
        pr_number: Pull request number the review comment belongs to (must be positive)
        comment_id: Review comment ID to reply to (must be positive)
        body: Reply text in Markdown (required, cannot be empty)
        reference_name: Optional reference project name. When set, the reply is
            posted to that project's GitHub repository instead of the workspace
            repository.

    Returns:
        "Replied to review comment <comment_id> on PR #<pr_number> — <url>", or
        error message string.
    """
    try:
        manager = _pr_manager(reference_name)
        reply = manager.reply_to_review_comment(pr_number, comment_id, body)
        # Empty CommentData carries id == 0, not number == 0 as issues do
        if not reply["id"]:
            return (
                f"Error: failed to reply to review comment {comment_id} "
                f"on PR #{pr_number}{ref_suffix(reference_name)}"
            )
        return (
            f"Replied to review comment {comment_id} on PR #{pr_number} — "
            f"{reply['url']}"
        )
    except Exception as e:
        return tool_error(e)


@_legacy_tool
@log_function_call
def github_review_thread_resolve(
    pr_number: int,
    thread_id: str,
    reference_name: str | None = None,
) -> str:
    """Resolve an inline PR review thread. This writes to GitHub.

    Args:
        pr_number: Pull request number the review thread belongs to (must be positive)
        thread_id: GraphQL node ID of the review thread to resolve
        reference_name: Optional reference project name. When set, the thread is
            resolved on that project's GitHub repository instead of the workspace
            repository.

    Returns:
        "Resolved review thread <thread_id> on PR #<pr_number>", or error message
        string.
    """
    try:
        manager = _pr_manager(reference_name)
        resolved = manager.resolve_review_thread(pr_number, thread_id)
        if not resolved:
            return (
                f"Error: failed to resolve review thread {thread_id} "
                f"on PR #{pr_number}{ref_suffix(reference_name)}"
            )
        return (
            f"Resolved review thread {thread_id} on PR #{pr_number}"
            f"{ref_suffix(reference_name)}"
        )
    except Exception as e:
        return tool_error(e)


@_legacy_tool
@log_function_call
def github_pr_create(
    title: str,
    body: str = "",
    head: str | None = None,
    base: str | None = None,
    body_file: str | None = None,
) -> str:
    """Open a real pull request on this repository. This writes to GitHub.

    Args:
        title: Pull request title (required, cannot be empty)
        body: Pull request description in Markdown (default: empty)
        head: Source branch (default: the currently checked-out branch)
        base: Target branch (default: resolved for head — the issue's Base
            Branch, an open PR's base, the merge-base parent, or the default
            branch — and verified on origin)
        body_file: Optional project-relative path whose content becomes the
            description (a leading UTF-8 BOM is dropped). Same path rules as
            read_file, so gitignored paths are refused. Mutually exclusive with
            a non-empty body.

    Returns:
        "Created PR #<number> — <url>", or an error message string. Passing
        both body and body_file, or a body_file that cannot be read or is
        refused, is returned as an error without creating anything. When base
        is omitted, these errors are also returned without creating anything:
        "Error: issue #N: <sentence>" (malformed Base Branch section),
        "Error: could not determine base branch for <head>",
        "Error: base branch '<base>' not found on origin",
        "Error: could not verify base branch '<base>' on origin: <cause>".
    """
    # Lazy imports: keep PyGithub/GitPython off the server startup import path
    from mcp_workspace.git_operations import (
        get_current_branch_name,
        probe_origin_branch,
    )
    from mcp_workspace.github_operations.pr_manager import PullRequestManager

    try:
        body = cast(str, _resolve_body(body, body_file, conflict=bool(body)))
        if not title.strip():
            return "Error: PR title cannot be empty"
        # Raises ValueError when _project_dir is unset, caught below
        manager = PullRequestManager(project_dir=_project_dir)
        # The constructor rejects a missing project_dir, so it is a Path by now
        project_dir = cast(Path, _project_dir)
        head = head or get_current_branch_name(project_dir)
        if not head:
            return "Error: could not determine the current branch for head"
        if not base:
            base, error = _resolve_base_branch(project_dir, head, manager)
            if error:
                return error
            if not base:
                return f"Error: could not determine base branch for {head}"
            try:
                probe = probe_origin_branch(project_dir, base)
            except Exception as e:  # pylint: disable=broad-exception-caught
                return f"Error: could not verify base branch '{base}' on origin: {e}"
            if probe["exists"] is None:
                cause = probe["stderr"] or probe["error"]
                return (
                    f"Error: could not verify base branch '{base}' on origin: {cause}"
                )
            if not probe["exists"]:
                return f"Error: base branch '{base}' not found on origin"
        if head == base:
            return f"Error: head and base are the same branch ({head})"
        for name in (head, base):
            # Reuse the library's branch rules rather than restating them
            # pylint: disable-next=protected-access
            if not manager._validate_branch_name(name):
                return f"Error: invalid branch name: {name}"
        pr = manager.create_pull_request(
            title=title,
            head_branch=head,
            base_branch=base,
            body=body,
        )
        # create_pull_request's swallowed-failure sentinel is {}, not number == 0
        if not pr.get("number"):
            return "Error: PR creation failed - no pull request was created"
        return f"Created PR #{pr['number']} — {pr['url']}"
    except Exception as e:
        return tool_error(e)


def _resolve_base_branch(
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


@_legacy_tool
@log_function_call
def get_base_branch() -> str:
    """Detect the base branch for the current branch.

    Returns:
        Branch name string; "Error: issue #N: …" when the linked issue's Base
        Branch section is malformed (no fallback); "main" when nothing could be
        detected.

    Raises:
        ValueError: If the project directory has not been set.
    """
    # Lazy import: keeps PyGithub/GitPython off the server startup import path
    from mcp_workspace.git_operations.branch_queries import get_current_branch_name
    from mcp_workspace.github_operations.pr_manager import PullRequestManager

    if _project_dir is None:
        raise ValueError("Project directory has not been set")

    pr_manager: PullRequestManager | None = None

    try:
        pr_manager = PullRequestManager(_project_dir)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("GitHub manager initialization failed", exc_info=True)

    try:
        branch = get_current_branch_name(_project_dir)
        if branch is None:
            return "main"
        base, error = _resolve_base_branch(_project_dir, branch, pr_manager)
        if error is not None:
            return error
        if base is None:
            return "main"
        return base
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("Base branch detection failed", exc_info=True)
        return "main"


@_legacy_tool
@log_function_call
def check_file_size(
    max_lines: int | None = None, show_allowlisted: bool = False
) -> str:
    """Check file line counts against threshold.

    Counts lines in every UTF-8 file under the project directory — all file
    types, tracked or not — excluding `.git/` and anything the project-root
    `.gitignore` matches. Nested `.gitignore` files are not read.

    Args:
        max_lines: Maximum allowed lines per file. When omitted, the default
            comes from the server's --file-size-limit flag, falling back to
            600 if that flag was not given.
        show_allowlisted: List only the `.large-files-allowlist` entries,
            each with its line count, `not scanned` or `missing`, largest
            first and uncapped; entries that can be removed are marked.
            This is a listing, never a failure — the gate is the call
            without this flag.

    Returns:
        Formatted report of files exceeding the threshold, or the
        allowlist listing when show_allowlisted is True.

    Raises:
        ValueError: If the project directory has not been set.
    """
    if _project_dir is None:
        raise ValueError("Project directory has not been set")
    effective = max_lines if max_lines is not None else _file_size_limit
    if effective is None:
        effective = 600
    allowlist_path = _project_dir / ".large-files-allowlist"
    allowlist = load_allowlist(allowlist_path)
    if show_allowlisted:
        return render_allowlisted(_project_dir, effective, allowlist)
    result = check_file_sizes(_project_dir, max_lines=effective, allowlist=allowlist)
    return render_output(result, effective)


@_legacy_tool
@log_function_call
async def check_branch_status(
    max_log_lines: int = 300,
    ci_timeout: int = 300,
    pr_timeout: int = 0,
    fail_on_reviews: bool | None = None,
) -> str:
    """Check comprehensive branch status: git state, CI, PR, tasks.

    Args:
        max_log_lines: Maximum CI log lines to include (default 300).
        ci_timeout: Seconds to poll for CI completion. 0 disables polling.
        pr_timeout: Seconds to poll for PR existence. 0 disables polling.
        fail_on_reviews: Enable the review-gate header. When omitted, uses the
            server's --fail-on-reviews default (off unless set).

    Returns:
        Formatted branch status report for LLM consumption.

    Raises:
        ValueError: If the project directory has not been set.
    """
    # Lazy import: keeps PyGithub/GitPython off the server startup import path
    from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

    if _project_dir is None:
        raise ValueError("Project directory has not been set")
    effective = fail_on_reviews if fail_on_reviews is not None else _fail_on_reviews
    return await async_poll_branch_status(
        _project_dir,
        max_log_lines=max_log_lines,
        ci_timeout=ci_timeout,
        pr_timeout=pr_timeout,
        fail_on_reviews=effective,
    )


class FastMCPSink:
    """ToolSink that registers each spec on a FastMCP server."""

    def __init__(self, mcp: FastMCP) -> None:
        self._mcp = mcp

    def add(self, spec: ToolSpec) -> None:
        """Register one spec under its name and description.

        Args:
            spec: The spec to register.
        """
        self._mcp.add_tool(spec.fn, name=spec.name, description=spec.description)


def _configure_legacy(project_dir: Path, settings: dict[str, Any]) -> None:
    """Apply the settings to the module globals the legacy tools read.

    Temporary: shrinks as tool groups move into mcp_workspace.toolset.

    Args:
        project_dir: Workspace root.
        settings: The keyword settings passed to create_server.
    """
    set_project_dir(project_dir)
    set_file_size_limit(settings.get("file_size_limit"))
    set_fail_on_reviews(settings.get("fail_on_reviews", False))
    set_enforce_base_branch_format(settings.get("enforce_base_branch_format", True))
    set_reference_projects(settings.get("reference_projects") or {})


def create_server(project_dir: Path, **settings: Any) -> FastMCP:
    """Build a FastMCP server with every workspace tool registered.

    Args:
        project_dir: Workspace root the tools operate in.
        **settings: Keyword settings forwarded to tool_specs.

    Returns:
        A new FastMCP server.
    """
    mcp = FastMCP("File System Service", instructions=_INSTRUCTIONS)
    sink = FastMCPSink(mcp)
    for spec in tool_specs(project_dir, **settings):
        sink.add(spec)
    _configure_legacy(project_dir, settings)
    for fn in _LEGACY_TOOLS:
        mcp.add_tool(fn)
    return mcp


@log_function_call
def run_server(
    project_dir: Path,
    reference_projects: dict[str, ReferenceProject] | None = None,
    file_size_limit: int | None = None,
    fail_on_reviews: bool = False,
    enforce_base_branch_format: bool = True,
    read_max_lines: int | None = DEFAULT_READ_MAX_LINES,
) -> None:
    """Run the MCP server with the given project directory and optional reference projects.

    Args:
        project_dir: Path to the project directory
        reference_projects: Optional dictionary mapping project names to directory paths
        file_size_limit: Optional per-project default line limit for check_file_size
        fail_on_reviews: Per-server default for check_branch_status' review gate
        enforce_base_branch_format: Server-wide default for rejecting a malformed
            Base Branch section in github_issue_create / github_issue_edit
        read_max_lines: Full-read line limit for read_file and
            read_reference_file; None or 0 means no limit
    """
    logger.debug("Entering run_server function")

    mcp = create_server(
        project_dir,
        reference_projects=reference_projects,
        file_size_limit=file_size_limit,
        fail_on_reviews=fail_on_reviews,
        enforce_base_branch_format=enforce_base_branch_format,
        read_max_lines=read_max_lines,
    )

    # Run the server
    logger.info("Starting MCP server")
    logger.debug("About to call mcp.run()")
    mcp.run()
    logger.debug(
        "After mcp.run() call - this line will only execute if mcp.run() returns"
    )
