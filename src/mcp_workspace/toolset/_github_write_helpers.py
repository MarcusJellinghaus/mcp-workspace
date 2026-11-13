"""Validation and rendering helpers for the workspace.github tools."""

from pathlib import Path
from typing import Any

from mcp_workspace.file_tools import normalize_path
from mcp_workspace.file_tools.line_endings import describe_line_endings
from mcp_workspace.toolset._context import (
    WorkspaceContext,
    check_readable,
    check_writable,
)
from mcp_workspace.toolset._github_common import (
    api_error,
    issue_manager,
    ref_suffix,
    repo_access_error,
)


def check_labels(
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


def check_base_branch(ctx: WorkspaceContext, body: str | None) -> str | None:
    """Reject a multi-line or invalid ref name ### Base Branch before any write.

    Args:
        ctx: Context holding the enforce_base_branch_format setting.
        body: Candidate issue body, or None when the caller is not changing
            the body (as in github_issue_edit).

    Returns:
        An error string naming the problem, the fix, and the section's first
        line (or invalid value), or None when the section is absent, empty,
        a single valid ref name, or the check is disabled.
    """
    if not ctx.enforce_base_branch_format:
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


def resolve_assignees(manager: Any, logins: list[str]) -> list[str]:
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


def edit_change_lines(
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
    # check_labels accepts a differently-cased name: requesting "Bug" lands
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


def resolve_body(
    ctx: WorkspaceContext, body: str | None, body_file: str | None, conflict: bool
) -> str | None:
    """Return the body to send: body unchanged, or body_file's text verbatim.

    The file is read under read_file's rules (gitignore boundary unless
    .mcp-file-access exposes the path, project containment). A leading UTF-8
    BOM is dropped; line endings are kept.

    Args:
        ctx: Context whose project_dir body_file is relative to.
        body: Inline body passed by the caller
        body_file: Project-relative path to read the body from, or None
        conflict: Whether body counts as passed alongside body_file

    Returns:
        body when body_file is None, otherwise the file's text.

    Raises:
        ValueError: conflict is True, the path is gitignored and not exposed
            by .mcp-file-access / outside the project / not a file, or the
            file is not UTF-8.
    """
    if body_file is None:
        return body
    if conflict:
        raise ValueError("pass either body or body_file, not both")
    check_readable(ctx, body_file)
    abs_path, _ = normalize_path(body_file, ctx.project_dir)
    if not abs_path.is_file():
        raise ValueError(f"body_file '{body_file}' not found or not a file")
    try:
        # newline="" keeps CRLF; utf-8-sig drops a leading BOM
        with open(abs_path, encoding="utf-8-sig", newline="") as f:
            return f.read()
    except UnicodeDecodeError as e:
        raise ValueError(f"body_file '{body_file}' is not valid UTF-8") from e


def check_body_target(ctx: WorkspaceContext, body_file: str) -> tuple[Path, str]:
    """Validate a body_file write target under save_file's path rules.

    Args:
        ctx: Context whose project_dir body_file is relative to.
        body_file: Project-relative path the body is to be written to.

    Returns:
        (absolute path, project-relative path with forward slashes).

    Raises:
        ValueError: path gitignored and not exposed by .mcp-file-access /
            read-only by .mcp-file-access / outside the project / an existing
            directory.
    """
    check_writable(ctx, body_file)
    abs_path, rel_path = normalize_path(body_file, ctx.project_dir)
    if abs_path.is_dir():
        raise ValueError(f"body_file '{body_file}' is a directory")
    return abs_path, rel_path.replace("\\", "/")


def save_body(abs_path: Path, display_path: str, body: str) -> str:
    """Write body verbatim (UTF-8, no BOM, line endings kept); return the pointer line.

    Args:
        abs_path: Target path, validated by check_body_target.
        display_path: Project-relative path shown in the pointer line.
        body: Raw issue body.

    Returns:
        E.g. ``"(body saved to x.md, 2 lines, CRLF)"``, or
        ``"(body saved to x.md: empty)"`` for an empty body.
    """
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    # Not save_file_util: it converts line endings; newline="" writes verbatim
    with open(abs_path, "w", encoding="utf-8", newline="") as f:
        f.write(body)
    if not body:
        return f"(body saved to {display_path}: empty)"
    return f"(body saved to {display_path}, {describe_line_endings(body)})"


def subissue_write(
    ctx: WorkspaceContext,
    parent_number: int,
    child_number: int,
    unlink: bool,
    reference_name: str | None,
) -> str:
    """Link or unlink a sub-issue and render the outcome.

    Args:
        ctx: Context holding the project directory and reference projects.
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
        manager = issue_manager(ctx, reference_name)
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
