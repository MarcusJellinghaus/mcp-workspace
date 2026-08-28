"""MCP server exposing workspace file, search, git, and GitHub tools."""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

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
    """
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.issues import IssueManager

    if reference_name is None:
        return IssueManager(project_dir=_project_dir)
    return IssueManager(repo_url=get_reference_repo_url(reference_name))


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
            return f"Error: Issue #{number} not found"
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
        issues = manager.list_issues(
            state=state,
            labels=labels,
            assignee=assignee,
            since=since_dt,
            max_results=max_results,
        )
        return format_issue_list(issues, max_results)
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
            # pylint: disable-next=protected-access
            api_base_url = manager._repo_identifier.api_base_url
            return f"Error: Could not access repository (tried {api_base_url})"
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
    """Search GitHub issues and pull requests in a single repository.

    Scoped to the workspace repository, or to the reference project named by
    reference_name. Additional qualifiers can be included inline in the query
    string (e.g., "fix login author:marcus").

    Args:
        query: Search query text
        state: Filter by state - "open" or "closed"
        labels: Filter by label names
        assignee: Filter by assignee username
        sort: Sort by "comments", "created", or "updated"
        order: Sort order - "asc" or "desc"
        max_results: Maximum results to return (default: 30)
        reference_name: Optional reference project name. When set, reads from
            that project's GitHub repository instead of the workspace repository.

    Returns:
        Compact summary lines, or error message string.
    """
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.formatters import format_search_results

    try:
        manager = _issue_manager(reference_name)
        repo = manager._get_repository()  # pylint: disable=protected-access
        if not repo:
            # pylint: disable-next=protected-access
            api_base_url = manager._repo_identifier.api_base_url
            return f"Error: Could not access repository (tried {api_base_url})"
        has_qualifier = re.search(
            r"(?:^|\s)is:(issue|pull-request)", query, re.IGNORECASE
        )
        if not has_qualifier:
            query = query + " is:issue is:pull-request"
        full_query = f"repo:{repo.full_name} {query}"
        qualifiers: Dict[str, str] = {"query": full_query}
        if state:
            qualifiers["state"] = state
        if labels:
            qualifiers["labels"] = ",".join(labels)
        if assignee:
            qualifiers["assignee"] = assignee
        if sort:
            qualifiers["sort"] = sort
        if order:
            qualifiers["order"] = order
        # pylint: disable=protected-access
        results = manager._github_client.search_issues(**qualifiers)
        items = []
        for i, item in enumerate(results):
            if i >= max_results:
                break
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
        result = format_search_results(items, max_results)
        if not has_qualifier:
            result += "\n(auto-added: is:issue is:pull-request)"
        return result
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
