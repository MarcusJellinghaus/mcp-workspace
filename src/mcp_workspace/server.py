"""MCP server exposing workspace file, search, git, and GitHub tools."""

import asyncio
import logging
import re
from datetime import datetime
from itertools import islice
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from mcp.server.fastmcp import FastMCP
from mcp_coder_utils.log_utils import log_function_call

from mcp_workspace.checks.file_sizes import (
    check_file_sizes,
    load_allowlist,
    render_output,
)
from mcp_workspace.file_tools import append_file as append_file_util
from mcp_workspace.file_tools import delete_directory as delete_directory_util
from mcp_workspace.file_tools import delete_file as delete_file_util
from mcp_workspace.file_tools import edit_file as edit_file_util
from mcp_workspace.file_tools import list_directory_tree
from mcp_workspace.file_tools import list_files as list_files_util
from mcp_workspace.file_tools import move_file as move_file_util
from mcp_workspace.file_tools import normalize_path
from mcp_workspace.file_tools import read_file as read_file_util
from mcp_workspace.file_tools import save_file as save_file_util
from mcp_workspace.file_tools import search_files as search_files_util
from mcp_workspace.file_tools.directory_utils import is_path_gitignored
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.server_reference_tools import (
    get_reference_project_path,
    get_reference_repo_url,
)
from mcp_workspace.server_reference_tools import register as register_reference_tools
from mcp_workspace.server_reference_tools import (
    set_reference_projects,
)

if TYPE_CHECKING:
    # Type-only: does not execute, so PyGithub stays off the startup import path
    from mcp_workspace.github_operations.issues import IssueManager

# Initialize loggers
logger = logging.getLogger(__name__)

# Create a FastMCP server instance
mcp = FastMCP("File System Service")
register_reference_tools(mcp)

# Store the project directory as a module-level variable
_project_dir: Optional[Path] = None

# Per-project default line limit for check_file_size (set via --file-size-limit)
_file_size_limit: Optional[int] = None

# Per-server default for check_branch_status' review gate (set via --fail-on-reviews)
_fail_on_reviews: bool = False

# Per-file locks for concurrent edit safety
_file_locks: dict[str, asyncio.Lock] = {}

# Workflow status labels are owned by `mcp-coder gh-tool set-status`, not by these tools
_STATUS_LABEL_PREFIX = "status-"

# Authenticated login for "@me", resolved once per process. A dict rather than a
# rebound global so pylint's global-statement never applies and tests reset it
# with a single .clear().
_login_cache: Dict[str, str] = {}


def _ref_suffix(reference_name: Optional[str]) -> str:
    """Return the clause naming a reference project, or "" for the workspace.

    Args:
        reference_name: Reference project name, or None for the workspace.

    Returns:
        " in reference project '<name>'", or "" when no name is given — the
        empty string keeps every workspace-path message byte-identical.
    """
    return "" if reference_name is None else f" in reference project '{reference_name}'"


def _check_labels(
    manager: Any,
    add: List[str],
    remove: List[str],
    reference_name: Optional[str] = None,
) -> Optional[str]:
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
    offenders = [
        n for n in (*add, *remove) if n.casefold().startswith(_STATUS_LABEL_PREFIX)
    ]
    if offenders:
        # `set-status` operates on the current checkout, so a reference
        # project's labels can only be advanced from that project's own clone.
        advice = "Use: mcp-coder gh-tool set-status <label>"
        if reference_name is not None:
            advice += f" from the '{reference_name}' project's own checkout"
        return (
            "Error: these tools do not modify status-* labels "
            f"({', '.join(offenders)}). {advice}"
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
            f"Error: unknown label(s){_ref_suffix(reference_name)}: "
            f"{', '.join(unknown)}"
        )
    return None


def _resolve_assignees(manager: Any, logins: List[str]) -> List[str]:
    """Resolve '@me' to the authenticated login, cached per process.

    Args:
        manager: An IssueManager instance used to read the authenticated user.
        logins: Requested assignee logins, possibly containing "@me".

    Returns:
        The logins with "@me" replaced by the authenticated username.
    """
    if "@me" in logins and "login" not in _login_cache:
        # Not get_authenticated_username(): that re-reads the token via
        # get_github_token() and would ignore a token passed to the manager.
        # pylint: disable=protected-access
        _login_cache["login"] = manager._github_client.get_user().login
    return [_login_cache["login"] if name == "@me" else name for name in logins]


def _normalize_newlines(text: Optional[str]) -> str:
    r"""Return text with CRLF and CR line endings folded to LF.

    Args:
        text: Text to normalize, or None for an absent body.

    Returns:
        The text with "\r\n" and "\r" replaced by "\n"; "" when text is None.
    """
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def _edit_change_lines(
    issue: Any,
    title: Optional[str],
    body: Optional[str],
    state: Optional[str],
    add_labels: Optional[List[str]],
    remove_labels: Optional[List[str]],
    assignees: List[str],
) -> List[str]:
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
    """
    if _project_dir is None:
        return  # Can't check without project_dir; other validation will catch this
    # Normalize to relative path for gitignore checking
    path = Path(file_path)
    if path.is_absolute():
        try:
            file_path = str(path.relative_to(_project_dir))
        except ValueError:
            return  # Path outside project dir — other validation handles this
    if is_path_gitignored(file_path, _project_dir):
        raise ValueError(
            f"File '{file_path}' is excluded by .gitignore and cannot be accessed. "
            "Use list_directory() to see available files."
        )


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
def set_file_size_limit(limit: Optional[int]) -> None:
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


@mcp.tool()
@log_function_call
def search_files(
    glob: Optional[str] = None,
    pattern: Optional[str] = None,
    context_lines: int = 0,
    max_results: int = 50,
    max_result_lines: int = 200,
) -> Dict[str, Any]:
    """Search file contents by regex and/or find files by glob pattern.

    Modes:
        - File search: provide `glob` to find files by path pattern (like find)
        - Content search: provide `pattern` (regex) to search inside files (like grep)
        - Combined: both to search content within matching files

    Args:
        glob: File path pattern (e.g. "**/*.py", "tests/**/test_*.py")
        pattern: Python regex to match file contents. Invalid regex patterns are
            automatically treated as literal text. (e.g. "def foo", "TODO.*fix")
        context_lines: Lines of context around each match (0 = match line only)
        max_results: Maximum number of matches or files returned (default 50)
        max_result_lines: Hard cap on total output lines (default 200)

    Returns:
        Dict with matches (content search) or file list (file search),
        plus truncated flag if results were capped.

    Raises:
        ValueError: If the project directory has not been set.
    """
    if _project_dir is None:
        raise ValueError("Project directory has not been set")

    return search_files_util(
        project_dir=_project_dir,
        glob=glob,
        pattern=pattern,
        context_lines=context_lines,
        max_results=max_results,
        max_result_lines=max_result_lines,
    )


@mcp.tool()
@log_function_call
def list_directory(path: str = ".", dirs_only: bool = False) -> List[str]:
    """List files and directories in the project directory.

    Args:
        path: Scope listing to a subtree (relative to project root).
            Defaults to "." (entire project).
        dirs_only: Show only directories, each with trailing "/".

    Returns:
        A list of path strings: files, directories (trailing ``/``),
        collapsed summaries (``dir/ (N files)``), or a truncation line
        when output exceeds the internal limit.

    Raises:
        ValueError: If the project directory has not been set or the
            path points to a file instead of a directory.
    """
    try:
        if _project_dir is None:
            raise ValueError("Project directory has not been set")

        # Validate path — normalize_path handles traversal attacks
        abs_path, rel_path = normalize_path(path, _project_dir)

        # If path points to a file, return error
        if abs_path.is_file():
            raise ValueError(
                f"'{path}' is a file, not a directory. Use read_file() instead."
            )

        logger.info(
            "Listing files in project directory: %s (path=%s)",
            _project_dir,
            path,
        )
        # Explicitly pass project_dir to list_files_util
        raw_files = list_files_util(path, project_dir=_project_dir, use_gitignore=True)

        # Build tree, collapse, render, truncate
        return list_directory_tree(raw_files, base_path=rel_path, dirs_only=dirs_only)
    except Exception as e:
        logger.error("Error listing project directory: %s", str(e))
        raise


@mcp.tool()
@log_function_call
def read_file(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    with_line_numbers: Optional[bool] = None,
) -> str:
    """Read a file, or a line slice via start_line/end_line.

    Args:
        file_path: Path to the file to read (relative to project directory)
        start_line: First line to return (1-based, inclusive). Requires end_line.
        end_line: Last line to return (1-based, inclusive). Requires start_line.
        with_line_numbers: Prefix lines with line numbers. Defaults to True for
            sliced reads, False for full reads.

    Returns:
        The contents of the file as a string

    Raises:
        ValueError: If file_path is not a non-empty string or the
            project directory has not been set.
    """
    if not file_path or not isinstance(file_path, str):
        logger.error("Invalid file path parameter: %s", file_path)
        raise ValueError(f"File path must be a non-empty string, got {type(file_path)}")

    if _project_dir is None:
        raise ValueError("Project directory has not been set")

    _check_not_gitignored(file_path)

    logger.info("Reading file: %s", file_path)
    try:
        content = read_file_util(
            file_path,
            project_dir=_project_dir,
            start_line=start_line,
            end_line=end_line,
            with_line_numbers=with_line_numbers,
        )
        return content
    except Exception as e:
        logger.error("Error reading file: %s", str(e))
        raise


@mcp.tool()
@log_function_call
def save_file(file_path: str, content: str) -> bool:
    """Write a file, creating parent directories as needed.

    Auto-creates parent directories if they do not exist.

    Args:
        file_path: Path to the file to write to (relative to project directory)
        content: Content to write to the file

    Returns:
        True if the file was written successfully

    Raises:
        ValueError: If file_path is not a non-empty string, content is
            not a string, or the project directory has not been set.
    """
    if not file_path or not isinstance(file_path, str):
        logger.error("Invalid file path parameter: %s", file_path)
        raise ValueError(f"File path must be a non-empty string, got {type(file_path)}")

    if content is None:  # defense-in-depth for direct callers
        logger.warning("Content is None, treating as empty string")  # type: ignore[unreachable]
        content = ""
    elif not isinstance(content, str):
        logger.error("Invalid content type: %s", type(content))  # type: ignore[unreachable]
        raise ValueError(f"Content must be a string, got {type(content)}")

    if _project_dir is None:
        raise ValueError("Project directory has not been set")

    _check_not_gitignored(file_path)

    logger.info("Writing to file: %s", file_path)
    try:
        success = save_file_util(file_path, content, project_dir=_project_dir)
        return success
    except Exception as e:
        logger.error("Error writing to file: %s", str(e))
        raise


@mcp.tool()
@log_function_call
def append_file(file_path: str, content: str) -> bool:
    """Append content to the end of a file.

    Args:
        file_path: Path to the file to append to (relative to project directory)
        content: Content to append to the file

    Returns:
        True if the content was appended successfully

    Raises:
        ValueError: If file_path is not a non-empty string, content is
            not a string, or the project directory has not been set.
    """
    if not file_path or not isinstance(file_path, str):
        logger.error("Invalid file path parameter: %s", file_path)
        raise ValueError(f"File path must be a non-empty string, got {type(file_path)}")

    if content is None:  # defense-in-depth for direct callers
        logger.warning("Content is None, treating as empty string")  # type: ignore[unreachable]
        content = ""
    elif not isinstance(content, str):
        logger.error("Invalid content type: %s", type(content))  # type: ignore[unreachable]
        raise ValueError(f"Content must be a string, got {type(content)}")

    if _project_dir is None:
        raise ValueError("Project directory has not been set")

    _check_not_gitignored(file_path)

    logger.info("Appending to file: %s", file_path)
    try:
        success = append_file_util(file_path, content, project_dir=_project_dir)
        return success
    except Exception as e:
        logger.error("Error appending to file: %s", str(e))
        raise


@mcp.tool()
@log_function_call
def delete_this_file(file_path: str) -> bool:
    """Delete a specified file from the filesystem.

    Handles files only, not directories — use delete_directory for directories.

    Args:
        file_path: Path to the file to delete (relative to project directory)

    Returns:
        True if the file was deleted successfully

    Raises:
        ValueError: If file_path is not a non-empty string or the
            project directory has not been set.
    """
    # delete_file does not work with Claude Desktop (!!!)  ;-)
    # Validate the file_path parameter
    if not file_path or not isinstance(file_path, str):
        logger.error("Invalid file path parameter: %s", file_path)
        raise ValueError(f"File path must be a non-empty string, got {type(file_path)}")

    if _project_dir is None:
        raise ValueError("Project directory has not been set")

    _check_not_gitignored(file_path)

    logger.info("Deleting file: %s", file_path)
    try:
        # Directly delete the file without user confirmation
        success = delete_file_util(file_path, project_dir=_project_dir)
        logger.info("File deleted successfully: %s", file_path)
        return success
    except Exception as e:
        logger.error("Error deleting file %s: %s", file_path, str(e))
        raise


@mcp.tool()
@log_function_call
def delete_directory(dir_path: str, recursive: bool = False) -> list[str]:
    """Delete a directory (empty by default; recursive=True for non-empty).

    Handles directories only — for files use delete_this_file. Deletes an empty
    directory by default; pass recursive=True to delete a non-empty tree. Missing
    directory is a no-op (returns a message, no error).

    Args:
        dir_path: Path to the directory to delete (relative to project directory)
        recursive: Delete the directory and all its contents when True

    Returns:
        List of deleted paths (relative to project directory), or a single
        message when the directory does not exist.

    Raises:
        ValueError: If dir_path is not a non-empty string, the project directory
            has not been set, the path is excluded by .gitignore, or the
            underlying deletion is rejected (outside project, project root,
            path-is-a-file, or non-empty without recursive).
    """
    if not dir_path or not isinstance(dir_path, str):
        logger.error("Invalid directory path parameter: %s", dir_path)
        raise ValueError(
            f"Directory path must be a non-empty string, got {type(dir_path)}"
        )

    if _project_dir is None:
        raise ValueError("Project directory has not been set")

    _check_not_gitignored(dir_path)

    logger.info("Deleting directory: %s", dir_path)
    try:
        return delete_directory_util(
            dir_path, project_dir=_project_dir, recursive=recursive
        )
    except Exception as e:
        logger.error("Error deleting directory %s: %s", dir_path, str(e))
        raise


@mcp.tool()
@log_function_call
def move_file(source_path: str, destination_path: str) -> bool:
    """Move or rename a file or directory (git-aware, preserves history).

    Git-aware: uses `git mv` for tracked files (preserving rename/history);
    falls back to a plain filesystem move for untracked files or non-git repos.

    Args:
        source_path: Source file/directory path (relative to project)
        destination_path: Destination path (relative to project)

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

    if _project_dir is None:
        raise ValueError("Project directory not configured")

    _check_not_gitignored(source_path)
    _check_not_gitignored(destination_path)

    try:
        # Call the underlying function (all logic is handled internally)
        result = move_file_util(source_path, destination_path, project_dir=_project_dir)

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


@mcp.tool()
@log_function_call
async def edit_file(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """Edit a file by exact string match; replace_all for multiple matches.

    Finds old_string in the file and replaces it with new_string.
    Empty old_string inserts new_string at the beginning of the file.
    Raises ValueError if old_string matches multiple locations
    (use replace_all=True to replace all).

    Args:
        file_path: Path to the file to edit (relative to project directory)
        old_string: Exact text to find and replace
        new_string: Replacement text
        replace_all: Replace all occurrences instead of requiring unique match

    Returns:
        Git-style unified diff showing the changes, or a message
        if the edit was already applied.

    Raises:
        ValueError: If file_path is not a non-empty string or the
            project directory has not been set.
    """
    if not file_path or not isinstance(file_path, str):
        raise ValueError(f"File path must be a non-empty string, got {type(file_path)}")

    if _project_dir is None:
        raise ValueError("Project directory has not been set")

    _check_not_gitignored(file_path)

    abs_path = str((_project_dir / file_path).resolve())
    lock = _file_locks.setdefault(abs_path, asyncio.Lock())
    async with lock:
        return edit_file_util(
            file_path, old_string, new_string, replace_all, _project_dir
        )


@mcp.tool()
@log_function_call
async def git(
    command: str,
    args: Optional[List[str]] = None,
    pathspec: Optional[List[str]] = None,
    search: Optional[str] = None,
    context: int = 3,
    max_lines: Optional[int] = None,
    compact: bool = True,
    reference_name: Optional[str] = None,
) -> str:
    """Run a read-only git command on the workspace or a reference project.

    Args:
        command: Git subcommand (log, diff, status, merge_base, fetch,
            show, branch, rev_parse, ls_tree, ls_files, ls_remote, check_ignore).
        args: Optional CLI flags (validated against per-command security allowlists).
        pathspec: Optional file paths appended after --.
        search: Optional regex to filter output (log, diff, show only).
        context: Lines of context around search matches (default 3).
        max_lines: Maximum output lines. Per-command defaults: log=50, diff=100, status=200, others=100.
        compact: If True, apply compact diff rendering (diff, show only).
        reference_name: Optional reference project name. When set, runs git against
            that project instead of the workspace.

    Returns:
        Command output, optionally filtered/truncated.

    Raises:
        ValueError: If no reference project is given and the project
            directory has not been set.
    """
    # Lazy import: keeps GitPython off the server startup import path
    from mcp_workspace.git_operations.read_operations import git as git_impl

    if reference_name is not None:
        project_dir = await get_reference_project_path(reference_name)
    else:
        if _project_dir is None:
            raise ValueError("Project directory has not been set")
        project_dir = _project_dir
    return await asyncio.to_thread(
        git_impl,
        command=command,
        project_dir=project_dir,
        args=args,
        pathspec=pathspec,
        search=search,
        context=context,
        max_lines=max_lines,
        compact=compact,
    )


def _issue_manager(reference_name: Optional[str]) -> "IssueManager":
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


def _repo_access_error(manager: "IssueManager") -> str:
    """Build the error text for a repository that could not be accessed.

    Args:
        manager: Manager whose repository lookup came back empty.

    Returns:
        Error text naming the API base URL that was tried, so a non-GitHub or
        unreachable host is distinguishable from a missing repository.
    """
    identifier = manager._repo_identifier  # pylint: disable=protected-access
    return f"Error: Could not access repository (tried {identifier.api_base_url})"


def _repo_full_name(manager: "IssueManager") -> Optional[str]:
    """Resolve the repository a manager reads from, for diagnostics.

    Args:
        manager: Manager to resolve the repository for.

    Returns:
        The "owner/repo" name, or None when the repository is not accessible.
    """
    repo = manager._get_repository()  # pylint: disable=protected-access
    return str(repo.full_name) if repo else None


@mcp.tool()
@log_function_call
def github_issue_view(
    number: int,
    include_comments: bool = True,
    max_lines: int = 200,
    reference_name: Optional[str] = None,
) -> str:
    """View a GitHub issue with full detail.

    Args:
        number: Issue number to view
        include_comments: Include issue comments (default: True)
        max_lines: Maximum output lines (default: 200)
        reference_name: Optional reference project name. When set, reads from
            that project's GitHub repository instead of the workspace repository.

    Returns:
        Formatted issue detail text, or error message string.
    """
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.formatters import format_issue_view

    try:
        manager = _issue_manager(reference_name)
        issue = manager.get_issue(number)
        if not issue["number"]:
            repo_full_name = _repo_full_name(manager)
            if repo_full_name is None:
                return _repo_access_error(manager)
            return f"Error: Issue #{number} not found in {repo_full_name}"
        comments = manager.get_comments(number) if include_comments else []
        return format_issue_view(issue, comments, max_lines)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
@log_function_call
def github_issue_list(
    state: str = "open",
    labels: Optional[List[str]] = None,
    assignee: Optional[str] = None,
    since: Optional[str] = None,
    max_results: int = 30,
    reference_name: Optional[str] = None,
) -> str:
    """List GitHub issues with optional filters.

    Args:
        state: Filter by state - "open", "closed", or "all" (default: "open")
        labels: Filter by label names
        assignee: Filter by assignee username, "none", or "*"
        since: Only issues updated after this ISO datetime string
        max_results: Maximum results to return (default: 30)
        reference_name: Optional reference project name. When set, reads from
            that project's GitHub repository instead of the workspace repository.

    Returns:
        Compact summary lines, or error message string.
    """
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.formatters import format_issue_list

    try:
        manager = _issue_manager(reference_name)
        since_dt = datetime.fromisoformat(since) if since else None
        # max_results is an unvalidated tool parameter; clamp before deriving
        # anything from it so a negative value cannot reach the notice as a
        # negative "shown" count.
        capped = max(0, max_results)
        # Over-fetch by one: no total count exists for issue listing, so the
        # surplus item is what proves more results exist. The formatter still
        # receives the capped value; it takes the notice's lower bound from the
        # over-fetched list, so a default-sized call renders "30 of 31+".
        issues = manager.list_issues(
            state=state,
            labels=labels,
            assignee=assignee,
            since=since_dt,
            max_results=capped + 1,
        )
        repo_full_name: Optional[str] = None
        if not issues:
            repo_full_name = _repo_full_name(manager)
            if repo_full_name is None:
                return _repo_access_error(manager)
        return format_issue_list(issues, capped, repo_full_name)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
@log_function_call
def github_pr_view(
    number: int,
    include_comments: bool = False,
    max_lines: int = 200,
    reference_name: Optional[str] = None,
) -> str:
    """View a GitHub pull request with full detail.

    Args:
        number: PR number to view
        include_comments: Include reviews, conversation and inline comments (default: False)
        max_lines: Maximum output lines (default: 200)
        reference_name: Optional reference project name. When set, reads from
            that project's GitHub repository instead of the workspace repository.

    Returns:
        Formatted PR detail text, or error message string.
    """
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.formatters import (
        InlineCommentData,
        ReviewData,
        format_pr_view,
    )
    from mcp_workspace.github_operations.issues.types import CommentData

    try:
        manager = _issue_manager(reference_name)
        repo = manager._get_repository()  # pylint: disable=protected-access
        if not repo:
            return _repo_access_error(manager)
        pr = repo.get_pull(number)
        pr_dict = {
            "number": pr.number,
            "title": pr.title,
            "body": pr.body,
            "state": pr.state,
            "head_branch": pr.head.ref,
            "base_branch": pr.base.ref,
            "draft": pr.draft,
            "merged": pr.merged,
        }
        reviews: Optional[List[ReviewData]] = None
        conversation_comments: Optional[List[CommentData]] = None
        inline_comments: Optional[List[InlineCommentData]] = None
        if include_comments:
            reviews = [
                ReviewData(user=r.user.login, state=r.state, body=r.body)
                for r in pr.get_reviews()
            ]
            conversation_comments = [
                CommentData(
                    id=c.id,
                    body=c.body,
                    user=c.user.login,
                    created_at=c.created_at.isoformat(),
                    updated_at=c.updated_at.isoformat() if c.updated_at else None,
                    url="",
                )
                for c in repo.get_issue(number).get_comments()
            ]
            inline_comments = [
                InlineCommentData(
                    path=c.path,
                    line=c.line,
                    user=c.user.login,
                    body=c.body,
                )
                for c in pr.get_review_comments()
            ]
        return format_pr_view(
            pr_dict, reviews, conversation_comments, inline_comments, max_lines
        )
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
@log_function_call
def github_search(
    query: str,
    state: Optional[str] = None,
    labels: Optional[List[str]] = None,
    assignee: Optional[str] = None,
    sort: Optional[str] = None,
    order: Optional[str] = None,
    max_results: int = 30,
    reference_name: Optional[str] = None,
) -> str:
    """Search one repository's GitHub issues; PRs need is:pull-request or is:pr.

    Automatically scoped to the workspace repository, or to the reference
    project named by reference_name. GitHub rejects a query that
    names no result type with HTTP 422, so "is:issue" is added when the query
    names none itself - the default is therefore issues only. Exactly five
    spellings suppress that default: "is:issue", "is:pr", "is:pull-request",
    "type:issue" and "type:pr". Nothing else does - a pull request search
    expressed through a PR-only qualifier such as "is:merged", "is:draft",
    "base:", "head:", "review:" or "merged:" must carry an explicit
    "is:pull-request" as well, or "is:issue" is added alongside it and no
    result can match. A negated qualifier ("-is:issue", "-is:open") never
    counts as naming a type or a state either, so it suppresses neither the
    added "is:issue" nor the "state" argument and is contradicted by the token
    this tool adds. "type:pull-request" is not GitHub syntax and is rejected
    with an error rather than sent, so that literal string cannot be used as
    free text either. Any other qualifier can be included inline (e.g.,
    "fix login is:pull-request author:marcus").

    Args:
        query: Search query text
        state: Filter by state - "open", "closed" or "all" (default: all
            states), matched case-insensitively.
            Ignored when the query already names a state inline
            ("is:open"/"is:closed"/"state:open"/"state:closed"), which wins -
            emitting both would ask GitHub for two states at once and match
            nothing
        labels: Filter by label names - multiple labels are ANDed (sent as
            label:"a" label:"b"), so only items carrying every label match.
            A label that is empty, whitespace-only, or contains a double quote
            is rejected
        assignee: Filter by assignee username - a value containing whitespace
            is rejected, since it would split into a qualifier plus stray
            free text
        sort: Sort by "comments", "created", or "updated"
        order: Sort order - "asc" or "desc"
        max_results: Maximum results to return (default: 30)
        reference_name: Optional reference project name. When set, searches
            that project's GitHub repository instead of the workspace repository.

    Returns:
        Compact summary lines, or error message string.
    """
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.formatters import format_search_results

    # Case-insensitive, matching every inline qualifier check below
    normalized_state = state.lower() if state else None
    if normalized_state and normalized_state not in ("open", "closed", "all"):
        return f"Error: Invalid state: {state}. Expected 'open', 'closed' or 'all'."
    # Reject rather than forward: live probing shows GitHub matches nothing
    # against "type:pull-request", so sending it on would return an empty
    # result indistinguishable from a genuine one.
    if re.search(r"(?:^|\s)type:pull-request(?![\w-])", query, re.IGNORECASE):
        return (
            "Error: Invalid qualifier 'type:pull-request': "
            "use 'is:pull-request' or 'is:pr'"
        )
    # GitHub search has no documented escape inside a quoted qualifier, so a
    # label carrying a double quote cannot be expressed - fail loudly instead
    # of guessing at an escape and silently matching something else. An empty
    # or whitespace-only label is unrepresentable for the same reason: it goes
    # out as label:"" and matches nothing, which reads as a genuine result.
    for label in labels or []:
        if not label.strip():
            return (
                f"Error: Invalid label {label!r}: "
                "a label cannot be empty or whitespace-only"
            )
        if '"' in label:
            return (
                f"Error: Invalid label {label!r}: "
                "a label containing a double quote cannot be searched"
            )
    # Unquoted in the query, so whitespace would split into "assignee:john"
    # plus a stray free-text term - a silently narrower search, not an error.
    if assignee and any(char.isspace() for char in assignee):
        return (
            f"Error: Invalid assignee {assignee!r}: "
            "a GitHub username cannot contain whitespace"
        )

    try:
        manager = _issue_manager(reference_name)
        repo = manager._get_repository()  # pylint: disable=protected-access
        if not repo:
            return _repo_access_error(manager)
        parts = [f"repo:{repo.full_name}"]
        # GitHub's /search/issues rejects a query that names no result type.
        # "type:pull-request" is deliberately absent - it is rejected above.
        if not re.search(
            r"(?:^|\s)(?:is:(?:issue|pr|pull-request)|type:(?:issue|pr))(?![\w-])",
            query,
            re.IGNORECASE,
        ):
            parts.append("is:issue")
        parts.append(query)
        # An inline state qualifier wins: adding the parameter's on top would
        # send "is:closed is:open", which GitHub matches nothing against.
        # Both spellings are live-verified to filter by state - see
        # test_github_search_live_state_spelling_honored - so trusting the
        # "state:" form here cannot silently drop the caller's state filter.
        inline_state = re.search(
            r"(?:^|\s)(?:is|state):(?:open|closed)(?![\w-])", query, re.IGNORECASE
        )
        if normalized_state in ("open", "closed") and not inline_state:
            parts.append(f"is:{normalized_state}")
        for label in labels or []:
            # Always quoted - this repo's own labels contain colons
            parts.append(f'label:"{label}"')
        if assignee:
            parts.append(f"assignee:{assignee}")
        kwargs: Dict[str, str] = {"query": " ".join(p for p in parts if p)}
        if sort:
            kwargs["sort"] = sort
        if order:
            kwargs["order"] = order
        # pylint: disable=protected-access
        results = manager._github_client.search_issues(**kwargs)
        items = []
        # max(0, ...) because islice rejects a negative stop, where the old
        # enumerate guard simply collected nothing.
        capped = max(0, max_results)
        # islice stops at max_results without pulling the next item, so a
        # default-sized search never fetches page 2 just to discard item 31.
        for item in islice(results, capped):
            item_labels = [label.name for label in item.labels] if item.labels else []
            items.append(
                {
                    "number": item.number,
                    "title": item.title,
                    "state": item.state,
                    "labels": item_labels,
                    "pull_request": item.pull_request is not None,
                }
            )
        # Read totalCount only after iterating, and only when we collected
        # something: PyGithub fills it from the first search page, which the
        # iteration above already paid for. Neither empty path needs the read,
        # for a different reason each:
        #   - clamped cap of 0: islice pulled nothing, so no page was fetched
        #     and the property would fall back to a separate per_page=1 request
        #     — the extra call this design exists to avoid.
        #   - positive cap, no matches: page 1 was fetched and cached
        #     totalCount == 0, so the read would be free, but the total is
        #     already known to be 0 and the "No results found." render has no
        #     use for it.
        # format_search_results owns both empty renders: it tells the two cases
        # apart from `capped` alone.
        return format_search_results(
            items, capped, results.totalCount if items else None
        )
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
@log_function_call
def github_issue_create(
    title: str,
    body: str = "",
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    reference_name: Optional[str] = None,
) -> str:
    """Create a real GitHub issue. This writes to GitHub.

    Targets the workspace repository, or a reference project's repository when
    reference_name is given. Workflow status labels (status-*) are rejected —
    those are applied with `mcp-coder gh-tool set-status <label>` from the
    target repository's own checkout. Other label names are validated against
    the target repository's labels before writing, so a typo cannot silently
    create a new label.

    Args:
        title: Issue title (required, cannot be empty)
        body: Issue description in Markdown (default: empty)
        labels: Label names to apply — each must already exist in the target
            repository
        assignees: GitHub usernames to assign; "@me" means the authenticated user
        reference_name: Optional reference project name. When set, the issue is
            created in that project's GitHub repository instead of the workspace
            repository.

    Returns:
        "Created issue #<number> — <url>" followed by the resulting labels and
        assignees, or error message string.
    """
    try:
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
                f"{_ref_suffix(reference_name)}"
            )
        # GitHub drops a non-assignable login or an unusable label silently, so
        # the resulting lists are the only way a caller sees what did not take
        return (
            f"Created issue #{issue['number']} — {issue['url']}\n"
            f"Labels: {', '.join(issue['labels']) or '(none)'}\n"
            f"Assignees: {', '.join(issue['assignees']) or '(none)'}"
        )
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
@log_function_call
def github_issue_edit(
    number: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
    add_assignees: Optional[List[str]] = None,
    state: Optional[str] = None,
) -> str:
    """Modify a real GitHub issue in this repository. This writes to GitHub.

    Only the arguments you pass are changed. Label changes are additive and
    subtractive, never a replacement of the whole set. Workflow status labels
    (status-*) are rejected on the add and the remove side — use
    `mcp-coder gh-tool set-status <label>` for those.

    The edit is not a transaction: if a later part fails, the earlier part
    stays applied. The result then opens with a warning naming which requested
    changes landed, followed by the resulting state. A failure that happens
    before any write instead opens with an error saying nothing was applied.

    Args:
        number: Issue number to edit (must be positive)
        title: New issue title; surrounding whitespace is stripped
        body: New issue description in Markdown
        add_labels: Label names to add — each must already exist in the repository
        remove_labels: Label names to remove; labels already absent are ignored
        add_assignees: Usernames to assign; "@me" means the authenticated user
        state: New issue state — only "open" or "closed" are accepted

    Returns:
        "Updated issue #<number> — <url> (state: <state>)" followed by the
        resulting labels and assignees. When nothing was applied, the same
        block opens with an error line and reads "Issue #<number> — ..."
        instead of "Updated issue". Or error message string.
    """
    # Lazy imports: keep PyGithub off the server startup import path
    from mcp_workspace.github_operations import GithubException
    from mcp_workspace.github_operations.issues import IssueManager
    from mcp_workspace.github_operations.issues.types import create_empty_issue_data

    try:
        # Pre-write validation. Nothing has been written yet, so a plain error
        # is honest — and it keeps the inner except below meaning exactly one
        # thing: the write sequence started and something after it failed.
        if number <= 0:
            return f"Error: invalid issue number: {number}"
        if title is not None and not title.strip():
            return "Error: Issue title cannot be empty"
        if state not in (None, "open", "closed"):
            return f"Error: state must be 'open' or 'closed', got: {state}"

        manager = IssueManager(project_dir=_project_dir)
        label_error = _check_labels(manager, add_labels or [], remove_labels or [])
        if label_error:
            return label_error
        resolved = _resolve_assignees(manager, add_assignees or [])

        reason = ""
        # edit_issue appends one entry per write call it issues, before
        # issuing it. Empty therefore means no write was ever issued — the
        # failure came before the first one, or the request had no write to
        # make. Either way nothing can have been written, which is the only
        # case in which claiming "no changes were made" is honest.
        attempted: List[str] = []
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
        except (GithubException, ValueError) as exc:
            # _handle_github_errors re-raises 401/403 and every ValueError,
            # including the identity check on edit_issue's own closing refetch.
            # Both can happen after part of the write landed.
            issue, reason = create_empty_issue_data(), str(exc)

        if reason:
            # The write sequence may have started and did not finish cleanly —
            # read the issue back so the caller learns what actually landed.
            reread_error = ""
            try:
                issue = manager.get_issue(number)
            except Exception as exc:
                issue, reread_error = create_empty_issue_data(), f": {exc}"
            if not issue["number"]:
                if not attempted:
                    return (
                        f"Error: issue #{number} not found or not accessible "
                        f"({reason}){reread_error} - no changes were made"
                    )
                return (
                    f"Error: edit of issue #{number} failed ({reason}) and the "
                    f"issue could not be re-read{reread_error} - these changes "
                    f"may or may not have been applied: {', '.join(attempted)}"
                )

        # Same signal as above: an empty write log means no write went out, so
        # nothing was applied — which makes both "partially failed" and
        # "Updated" untrue.
        failed_before_write = bool(reason) and not attempted
        lines: List[str] = []
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
        return f"Error: {e}"


@mcp.tool()
@log_function_call
def github_issue_comment(
    number: int,
    body: str,
    reference_name: Optional[str] = None,
) -> str:
    """Post a real comment on a GitHub issue. This writes to GitHub.

    The comment text is passed inline — no temporary file is needed, and
    multi-line Markdown is sent through unchanged.

    Args:
        number: Issue number to comment on (must be positive)
        body: Comment text in Markdown (required, cannot be empty)
        reference_name: Optional reference project name. When set, the comment is
            posted to that project's GitHub repository instead of the workspace
            repository.

    Returns:
        "Added comment to issue #<number> — <url>", or error message string.
    """
    try:
        manager = _issue_manager(reference_name)
        comment = manager.add_comment(number, body)
        # Empty CommentData carries id == 0, not number == 0 as issues do
        if not comment["id"]:
            return (
                f"Error: failed to add comment to issue #{number}"
                f"{_ref_suffix(reference_name)}"
            )
        return f"Added comment to issue #{number} — {comment['url']}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
@log_function_call
def github_label_list(
    search: Optional[str] = None,
    reference_name: Optional[str] = None,
) -> str:
    """List the labels defined in the workspace repository or a reference project.

    This only reads from GitHub.

    Args:
        search: Optional filter — case-insensitive substring matched against
            the label name or its description, as ``gh label list --search``
            does. Omit it to list every label.
        reference_name: Optional reference project name. When set, lists the labels
            of that project's GitHub repository instead of the workspace repository.

    Returns:
        One line per label, ``<name>  #<color>  <description>``, or
        "No labels found." when nothing matches, or error message string.
    """
    try:
        manager = _issue_manager(reference_name)
        # Raises rather than returning [] on API failure, so an empty list here
        # means the repository really has no labels
        labels = manager.get_available_labels()
        if search:
            query = search.lower()
            labels = [
                label
                for label in labels
                if query in label["name"].lower()
                or query in label["description"].lower()
            ]
        if not labels:
            return "No labels found."
        return "\n".join(
            f"{label['name']}  #{label['color']}  {label['description']}".rstrip()
            for label in labels
        )
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
@log_function_call
def github_pr_create(
    title: str,
    body: str = "",
    head: Optional[str] = None,
    base: Optional[str] = None,
) -> str:
    """Open a real pull request on this repository. This writes to GitHub.

    Args:
        title: Pull request title (required, cannot be empty)
        body: Pull request description in Markdown (default: empty)
        head: Source branch (default: the currently checked-out branch)
        base: Target branch (default: the repository's default branch)

    Returns:
        "Created PR #<number> — <url>", or error message string.
    """
    # Lazy imports: keep PyGithub/GitPython off the server startup import path
    from mcp_workspace.git_operations import (
        get_current_branch_name,
        get_default_branch_name,
    )
    from mcp_workspace.github_operations.pr_manager import PullRequestManager

    try:
        if not title.strip():
            return "Error: PR title cannot be empty"
        # Raises ValueError when _project_dir is unset, caught below
        manager = PullRequestManager(project_dir=_project_dir)
        # The constructor rejects a missing project_dir, so it is a Path by now
        project_dir = cast(Path, _project_dir)
        head = head or get_current_branch_name(project_dir)
        base = base or get_default_branch_name(project_dir)
        if not head:
            return "Error: could not determine the current branch for head"
        if not base:
            return "Error: could not determine the repository default branch for base"
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
        return f"Error: {e}"


@mcp.tool()
@log_function_call
def get_base_branch() -> str:
    """Detect the base branch for the current branch.

    Returns:
        Branch name string. Returns default branch name if detection fails.

    Raises:
        ValueError: If the project directory has not been set.
    """
    # Lazy import: keeps PyGithub/GitPython off the server startup import path
    from mcp_workspace.git_operations.base_branch import detect_base_branch
    from mcp_workspace.github_operations.issues import IssueManager
    from mcp_workspace.github_operations.pr_manager import PullRequestManager

    if _project_dir is None:
        raise ValueError("Project directory has not been set")

    issue_manager: Optional[IssueManager] = None
    pr_manager: Optional[PullRequestManager] = None

    try:
        issue_manager = IssueManager(project_dir=_project_dir)
        pr_manager = PullRequestManager(_project_dir)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("GitHub manager initialization failed", exc_info=True)

    try:
        result = detect_base_branch(
            _project_dir,
            issue_manager=issue_manager,
            pr_manager=pr_manager,
        )
        if result is None:
            return "main"
        return result
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("Base branch detection failed", exc_info=True)
        return "main"


@mcp.tool()
@log_function_call
def check_file_size(max_lines: Optional[int] = None) -> str:
    """Check file line counts against threshold.

    Args:
        max_lines: Maximum allowed lines per file. When omitted, the default
            comes from the server's --file-size-limit flag, falling back to
            600 if that flag was not given.

    Returns:
        Formatted report of files exceeding the threshold.

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
    result = check_file_sizes(_project_dir, max_lines=effective, allowlist=allowlist)
    return render_output(result, effective)


@mcp.tool()
@log_function_call
async def check_branch_status(
    max_log_lines: int = 300,
    ci_timeout: int = 300,
    pr_timeout: int = 0,
    fail_on_reviews: Optional[bool] = None,
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


@log_function_call
def run_server(
    project_dir: Path,
    reference_projects: Optional[Dict[str, ReferenceProject]] = None,
    file_size_limit: Optional[int] = None,
    fail_on_reviews: bool = False,
) -> None:
    """Run the MCP server with the given project directory and optional reference projects.

    Args:
        project_dir: Path to the project directory
        reference_projects: Optional dictionary mapping project names to directory paths
        file_size_limit: Optional per-project default line limit for check_file_size
        fail_on_reviews: Per-server default for check_branch_status' review gate
    """
    logger.debug("Entering run_server function")

    # Set the project directory
    set_project_dir(project_dir)

    # Set the per-project default file size limit
    set_file_size_limit(file_size_limit)

    # Set the per-server review-gate default
    set_fail_on_reviews(fail_on_reviews)

    # Set reference projects if provided
    if reference_projects:
        set_reference_projects(reference_projects)

    # Run the server
    logger.info("Starting MCP server")
    logger.debug("About to call mcp.run()")
    mcp.run()
    logger.debug(
        "After mcp.run() call - this line will only execute if mcp.run() returns"
    )
