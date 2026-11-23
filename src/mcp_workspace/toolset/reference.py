"""Tool group workspace.reference: read-only access to reference projects."""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, TypeVar

from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSink, tool_spec
from pydantic import Field

from mcp_workspace.file_tools import read_file as read_file_util
from mcp_workspace.file_tools import search_files as search_files_util
from mcp_workspace.file_tools.access_rules import access_rules_warning
from mcp_workspace.file_tools.file_access import (
    FileAccess,
    list_accessible_files,
    require_access,
)
from mcp_workspace.file_tools.file_operations import decode_lines, read_content
from mcp_workspace.file_tools.path_utils import ref_relative_path
from mcp_workspace.file_tools.search import search_paths
from mcp_workspace.reference_projects import ensure_available
from mcp_workspace.toolset._context import WorkspaceContext
from mcp_workspace.toolset._reference_freshness import (
    fallback_note,
    fetch_failure_note,
    fetch_if_stale,
    mark_fetched,
    with_notes,
)
from mcp_workspace.utils.url_credentials import scrub_credentials

if TYPE_CHECKING:
    # Type-only: does not execute, so GitPython stays off the startup import path
    from mcp_workspace.git_operations.ref_snapshot import RefSnapshot

logger = logging.getLogger(__name__)

# Every reference file is read-only, so only "not committed" is worth a label
_NOTE_EXPOSED = "(not committed)"

T = TypeVar("T")


async def reference_project_path(ctx: WorkspaceContext, name: str) -> Path:
    """Resolve a reference project name to its local path, ensuring availability.

    Args:
        ctx: Context holding the configured reference projects.
        name: Reference project name.

    Returns:
        Local filesystem path of the reference project.

    Raises:
        ValueError: If no reference project with the given name exists.
    """
    if name not in ctx.reference_projects:
        raise ValueError(f"Reference project '{name}' not found")
    project = ctx.reference_projects[name]
    if await ensure_available(
        project,
        locks=ctx.reference_state.clone_locks,
        failures=ctx.reference_state.clone_failures,
    ):
        mark_fetched(ctx, name)  # a fresh clone counts as a fresh fetch
    return project.path


def _notes(
    ctx: WorkspaceContext, name: str, where: str | None, no_default: bool
) -> list[str]:
    """Return the notes for one reference read, fetch-failure first.

    Args:
        ctx: Context holding the interval and fetch records.
        name: Reference project name.
        where: Ref and short SHA that was read, or None when no ref is known.
        no_default: True when the folder is a git repo without a usable
            origin default branch and was read locally.

    Returns:
        The notes to attach; empty for a normal result.
    """
    notes = [note for note in (fetch_failure_note(ctx, name, where),) if note]
    if no_default:
        notes.append(fallback_note(name))
    return notes


def _run_reference_read(
    ctx: WorkspaceContext,
    name: str,
    path: Path,
    at_ref: Callable[["RefSnapshot"], T],
    local: Callable[[Path], T],
) -> tuple[T, list[str]]:
    """Fetch if stale, then read at origin/<default> or the local folder (sync).

    Args:
        ctx: Context holding the reference state.
        name: Reference project name.
        path: Local folder of the reference project.
        at_ref: Reads from a snapshot of origin/<default>.
        local: Reads the local folder; used when there is no usable ref.

    Returns:
        The result and the notes to attach.

    Raises:
        Exception: The read's error, carrying the notes when there are any.
    """  # noqa: DOC502 - re-raised from at_ref / local / open_ref_snapshot
    # Lazy import: keeps GitPython off the server startup import path
    from mcp_workspace.git_operations.ref_snapshot import (
        RefFallback,
        RefSnapshot,
        open_ref_snapshot,
    )

    fetch_if_stale(ctx, name, path)
    notes: list[str] = []
    try:
        with open_ref_snapshot(path, name) as snap:
            if isinstance(snap, RefSnapshot):
                notes = _notes(ctx, name, snap.where, no_default=False)
                result = at_ref(snap)
            else:
                notes = _notes(
                    ctx, name, None, no_default=snap is RefFallback.NO_DEFAULT
                )
                result = local(path)
    except Exception as exc:  # pylint: disable=broad-exception-caught  # re-raised with the notes
        notes = notes or _notes(ctx, name, None, no_default=False)
        if not notes:
            raise
        error = with_notes(exc, notes)
    else:
        return result, notes
    raise error  # outside the except block: no unscrubbed __context__


async def _reference_call(
    ctx: WorkspaceContext,
    name: str,
    at_ref: Callable[["RefSnapshot"], T],
    local: Callable[[Path], T],
) -> tuple[T, list[str]]:
    """Run one reference read at origin/<default> (or the local folder) in a worker thread.

    Args:
        ctx: Context holding the reference projects and their state.
        name: Reference project name.
        at_ref: Reads from a snapshot of origin/<default>.
        local: Reads the local folder; used when there is no usable ref.

    Returns:
        The result and the notes to attach (fetch-failure first, then fallback).
    """
    path = await reference_project_path(ctx, name)
    return await asyncio.to_thread(_run_reference_read, ctx, name, path, at_ref, local)


def reference_repo_url(ctx: WorkspaceContext, name: str) -> str:
    """Resolve a reference project name to its configured repository URL.

    Synchronous and side-effect free — unlike reference_project_path(),
    this never calls ensure_available(), so it never clones.

    Args:
        ctx: Context holding the configured reference projects.
        name: Reference project name.

    Returns:
        The configured repository URL.

    Raises:
        ValueError: If no reference project with the given name exists, or
            the project has no URL configured.
    """
    if name not in ctx.reference_projects:
        raise ValueError(f"Reference project '{name}' not found")
    url = ctx.reference_projects[name].url
    if url is None:
        raise ValueError(f"Reference project '{name}' has no URL configured")
    return url


def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.reference tools bound to ctx.

    Args:
        sink: Receives one ToolSpec per tool.
        ctx: Settings and state the tools are bound to.
    """

    @log_function_call
    def get_reference_projects() -> dict[str, Any]:
        """Get the available reference projects as {"name", "url"} entries.

        Returns:
            Dictionary containing:
            - count: Number of available projects
            - projects: List of {"name", "url"} dicts, sorted by name
            - usage: Which tools accept a returned name as reference_name

        Read the returned usage value for how to use the names.
        """
        try:
            # Return structured dict instead of simple list because MCP tool responses
            # can be ambiguous when displaying arrays - items may appear concatenated
            # or unclear to LLMs. This format ensures clear communication.

            if not ctx.reference_projects:
                logger.info("No reference projects configured")
                return {
                    "count": 0,
                    "projects": [],
                    "usage": "No reference projects available",
                }

            projects = sorted(
                [
                    {
                        "name": p.name,
                        "url": scrub_credentials(p.url) if p.url is not None else None,
                    }
                    for p in ctx.reference_projects.values()
                ],
                key=lambda p: str(p["name"]),
            )
            logger.info(
                "Found %d reference projects: %s",
                len(projects),
                [p["name"] for p in projects],
            )

            return {
                "count": len(projects),
                "projects": projects,
                "usage": (
                    "Pass a name as reference_name to the reference file tools, git(), "
                    "and the GitHub read tools; issues can also be created, edited and "
                    "commented on"
                ),
            }

        except Exception as e:
            logger.error("Error getting reference projects: %s", str(e))
            raise

    @log_function_call
    async def read_reference_file(
        reference_name: Annotated[
            str, Field(description="Name of the reference project")
        ],
        file_path: Annotated[
            str,
            Field(
                description=(
                    "Path to the file to read (relative to reference project directory)"
                )
            ),
        ],
        start_line: Annotated[
            int | None,
            Field(
                description=(
                    "First line to return (1-based, inclusive). Requires end_line."
                )
            ),
        ] = None,
        end_line: Annotated[
            int | None,
            Field(
                description=(
                    "Last line to return (1-based, inclusive). Requires start_line."
                )
            ),
        ] = None,
        with_line_numbers: Annotated[
            bool | None,
            Field(
                description=(
                    "Prefix lines with line numbers. Defaults to True for "
                    "sliced reads, False for full reads."
                )
            ),
        ] = None,
    ) -> str:
        """Read a reference-project file, or a line slice via start_line/end_line.

        Returns:
            The contents of the file as a string. A full read beyond the
            configured limit (default 2000 lines) is cut, followed by a note
            giving the next start_line/end_line; an explicit range is returned
            in full.

        Raises:
            ValueError: If file_path is gitignored and not exposed by that
                project's .mcp-file-access.
        """

        def at_ref(snap: "RefSnapshot") -> str:
            rel = ref_relative_path(
                file_path, ctx.reference_projects[reference_name].path
            )
            return read_content(
                snap.read_bytes(rel, file_path),
                file_path,
                start_line=start_line,
                end_line=end_line,
                with_line_numbers=with_line_numbers,
                max_lines=ctx.read_max_lines,
            )

        def local(ref_path: Path) -> str:
            require_access(file_path, ref_path, FileAccess.READ_ONLY, reference=True)
            # The utility function handles all parameter validation and security checks
            return read_file_util(
                file_path,
                project_dir=ref_path,
                start_line=start_line,
                end_line=end_line,
                with_line_numbers=with_line_numbers,
                max_lines=ctx.read_max_lines,
            )

        content, notes = await _reference_call(ctx, reference_name, at_ref, local)
        if not notes:
            return content
        separator = "" if not content or content.endswith("\n") else "\n"
        return content + separator + "\n".join(notes)

    @log_function_call
    async def list_reference_directory(
        reference_name: Annotated[
            str, Field(description="Name of the reference project to list")
        ],
    ) -> list[str]:
        """List files and directories in a reference project directory.

        Returns:
            A list of filenames in the reference project directory, including
            the gitignored paths its .mcp-file-access exposes. Paths are
            forward-slash separated on every platform. A file line ends in
            `` (not committed)`` for a gitignored file that project's
            .mcp-file-access exposes; strip that suffix before passing the path
            to `read_reference_file`. When that rules file is invalid, the
            first line is a warning instead of a path.
        """

        def at_ref(snap: "RefSnapshot") -> list[str]:
            return snap.list_files()

        def local(ref_path: Path) -> list[str]:
            listing = list_accessible_files(".", ref_path)
            entries = [
                f"{rel} {_NOTE_EXPOSED}" if rel in listing.exposed_ignored else rel
                for rel in listing.files
            ]
            warning = access_rules_warning(listing.problems)
            if warning is not None:
                return [warning, *entries]
            return entries

        files, notes = await _reference_call(ctx, reference_name, at_ref, local)
        if not notes:
            return files
        return [*files, "\n".join(notes)]

    @log_function_call
    async def search_reference_files(
        reference_name: Annotated[
            str, Field(description="Name of the reference project")
        ],
        glob: Annotated[
            str | None,
            Field(
                description=(
                    "File path pattern with gitignore/wildmatch semantics — e.g. "
                    '"**/*.py", "tests/**/test_*.py", "/README.md" (root only). '
                    'Brace expansion is NOT supported: "{a,b}/f.py" matches a '
                    'literal "{a,b}" directory. Issue one call per alternative, '
                    'or widen to "*" and filter. A bare "*.py" is unanchored and '
                    "matches at any depth, unlike a shell glob. On Windows, "
                    "matching is case-insensitive by design, so a glob cannot "
                    "detect a filename casing mismatch — use `git ls-files`, "
                    "which reports the name as recorded in the index."
                )
            ),
        ] = None,
        pattern: Annotated[
            str | None,
            Field(
                description=(
                    "Python regex to match file contents. Invalid regex patterns "
                    "are automatically treated as literal text. "
                    '(e.g. "def foo", "TODO.*fix")'
                )
            ),
        ] = None,
        context_lines: Annotated[
            int,
            Field(
                description="Lines of context around each match (0 = match line only)"
            ),
        ] = 0,
        max_results: Annotated[
            int,
            Field(
                description="Maximum number of matches or files returned (default 50)"
            ),
        ] = 50,
        max_result_lines: Annotated[
            int, Field(description="Hard cap on total output lines (default 200)")
        ] = 200,
    ) -> dict[str, Any]:
        """Search file contents by regex and/or find files by glob pattern in a reference project.

        Modes:
            - File search: provide `glob` to find files by path pattern (like find)
            - Content search: provide `pattern` (regex) to search inside files (like grep)
            - Combined: both to search content within matching files

        Returns:
            Dict with matches (content search) or file list (file search),
            plus truncated flag if results were capped.
            Adds a "glob_note" key when the glob matched no files and contains
            "{", which wildmatch treats literally, distinguishing that from a
            genuine no-such-file result.
            A content search adds a "skipped_files" key listing project-relative
            paths that could not be read — a path rejected by the security check,
            or an unreadable file — present only when non-empty.
            Gitignored paths that .mcp-file-access exposes are included; a
            "warning" key appears while that rules file is invalid.
            Paths are forward-slash separated on every platform and can be
            passed straight back to `read_reference_file`.

        Raises:
            ValueError: If the glob matches nothing by construction (a gitignore
                comment, blank, negation-only, or unparseable pattern such as an
                unterminated "[").
        """

        def at_ref(snap: "RefSnapshot") -> dict[str, Any]:
            return search_paths(
                snap.list_files(),
                lambda path: decode_lines(snap.read_bytes(path)),
                glob,
                pattern,
                context_lines,
                max_results,
                max_result_lines,
            )

        def local(ref_path: Path) -> dict[str, Any]:
            return search_files_util(
                project_dir=ref_path,
                glob=glob,
                pattern=pattern,
                context_lines=context_lines,
                max_results=max_results,
                max_result_lines=max_result_lines,
            )

        result, notes = await _reference_call(ctx, reference_name, at_ref, local)
        if notes:
            result["freshness"] = "\n".join(notes)
        return result

    for fn in (
        get_reference_projects,
        read_reference_file,
        list_reference_directory,
        search_reference_files,
    ):
        sink.add(tool_spec(fn, group="workspace.reference", read_only=True))
