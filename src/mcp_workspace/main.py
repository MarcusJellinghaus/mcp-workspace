"""Main entry point for the MCP server."""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, NoReturn, Optional, Tuple

# Import logging utilities
from mcp_coder_utils.log_utils import setup_logging

from mcp_workspace import __version__
from mcp_workspace._ssl import ensure_truststore
from mcp_workspace.reference_projects import ReferenceProject, detect_and_verify_url
from mcp_workspace.traffic_log import set_traffic_log_context

# Create loggers
stdlogger = logging.getLogger(__name__)

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_FALLBACK_LOG_FILE = "logs/mcp_workspace_startup_error.log"
_HELP_TOKENS = frozenset({"-h", "--help", "--version"})


class StartupArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that raises ValueError instead of printing and exiting."""

    def error(self, message: str) -> NoReturn:
        """Raise ValueError(message) instead of printing and exiting.

        Raises:
            ValueError: Always.
        """
        raise ValueError(message)


def _shared_options_parser() -> argparse.ArgumentParser:
    """Build the four startup options needed to configure logging.

    Used as a ``parents=[...]`` template by both the pre-parser and the full
    parser, so the four option definitions live in exactly one place.

    Returns:
        An ``ArgumentParser`` holding ``--project-dir``, ``--log-level``,
        ``--log-file``, and ``--console-only``.
    """
    parser = StartupArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument(
        "--project-dir",
        type=str,
        help="Base directory for all file operations (required)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Set logging level (default: INFO). One of: DEBUG, INFO, WARNING, ERROR, CRITICAL.",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path for structured JSON logs (default: mcp_workspace_{timestamp}.log in project_dir/logs/).",
    )
    parser.add_argument(
        "--console-only",
        action="store_true",
        help="Log only to console, ignore --log-file parameter.",
    )
    return parser


def parse_args(
    argv: Optional[List[str]] = None,
) -> Tuple[argparse.Namespace, List[str]]:
    """Parse command line arguments.

    Returns:
        Tuple of the parsed arguments and any tokens argparse did not recognize.
    """
    parser = StartupArgumentParser(
        description="MCP File System Server - A Model Context Protocol server providing file operation tools",
        allow_abbrev=False,
        parents=[_shared_options_parser()],
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"mcp-workspace {__version__}",
        help="Show version number and exit",
    )
    parser.add_argument(
        "--reference-project",
        action="append",
        help="Reference project as key-value pairs: name=myproj,path=/path/to/dir,url=https://... (name and path required, url optional)",
    )
    parser.add_argument(
        "--file-size-limit",
        type=int,
        default=None,
        help="Default line limit for check_file_size when max_lines is omitted "
        "(must be > 0; falls back to 600 if not set).",
    )
    parser.add_argument(
        "--fail-on-reviews",
        action="store_true",
        help="Default for check_branch_status' review gate; the tool "
        "parameter overrides per call.",
    )
    parser.add_argument(
        "--enforce-base-branch-format",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reject a malformed `### Base Branch` section (more than one line) "
        "when creating or editing an issue body. Disable with "
        "--no-enforce-base-branch-format.",
    )
    return parser.parse_known_args(argv if argv is not None else sys.argv[1:])


def _pre_parse(argv: List[str]) -> argparse.Namespace:
    """Tolerantly extract the four options logging needs, ignoring the rest.

    Returns:
        The parsed namespace; unrecognized tokens are discarded.
    """
    parser = StartupArgumentParser(
        add_help=False, allow_abbrev=False, parents=[_shared_options_parser()]
    )
    return parser.parse_known_args(argv)[0]


def _validate_log_level(log_level: str) -> str:
    """Normalize and validate a log level string.

    Returns:
        The upper-cased, canonical level name.

    Raises:
        ValueError: If `log_level` is not one of the known level names.
    """
    normalized = log_level.upper()
    if normalized not in _LOG_LEVELS:
        raise ValueError(
            f"Invalid --log-level: {log_level}. Must be one of: {', '.join(_LOG_LEVELS)}"
        )
    return normalized


def _resolve_project_dir(project_dir_arg: Optional[str]) -> Optional[Path]:
    """Resolve the project directory, or None if missing/invalid.

    Returns:
        The resolved, canonical project directory, or None.
    """
    if not project_dir_arg:
        return None
    project_dir = Path(project_dir_arg)
    if not project_dir.exists() or not project_dir.is_dir():
        return None
    return project_dir.resolve()


def _resolve_log_file(
    pre_args: argparse.Namespace, project_dir: Optional[Path]
) -> Optional[str]:
    """Resolve the log file path to pass to `setup_logging`, or None.

    Returns:
        The log file path, or None for console-only / unresolved project dir.
    """
    console_only: bool = pre_args.console_only
    if console_only:
        return None
    log_file_arg: Optional[str] = pre_args.log_file
    if log_file_arg:
        return log_file_arg
    if project_dir is not None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logs_dir = project_dir / "logs"
        return str(logs_dir / f"mcp_workspace_{timestamp}.log")
    return None


def _has_real_file_handler() -> bool:
    """True if a FileHandler is attached to the root logger.

    Returns:
        True if a FileHandler is attached.
    """
    return any(
        isinstance(handler, logging.FileHandler)
        for handler in logging.getLogger().handlers
    )


def _handle_startup_failure(exc: Exception) -> None:
    """Log a startup failure, bootstrapping a fallback log file if needed."""
    if not _has_real_file_handler():
        try:
            setup_logging("INFO", _FALLBACK_LOG_FILE)
        except OSError:
            pass
    stdlogger.error("Startup failed", exc_info=exc)
    print(f"Error: {exc}", file=sys.stderr)


def validate_reference_projects(
    reference_args: List[str], project_dir: Path
) -> Dict[str, ReferenceProject]:
    """Parse and validate reference project arguments.

    Parses comma-separated KV pairs: name=proj,path=/dir,url=https://...
    Validates name and path are present. Logs warnings for invalid
    references and continues with valid ones only. Auto-renames duplicates.
    Filters out reference projects that overlap with project_dir.

    Returns:
        Dict mapping project names to validated ReferenceProject entries.

    Raises:
        ValueError: If explicit URL doesn't match detected git remote URL.
    """
    if not reference_args:
        return {}

    resolved_project_dir = project_dir.resolve()
    validated_projects: Dict[str, ReferenceProject] = {}

    for arg in reference_args:
        # Parse comma-separated key=value pairs
        pairs = dict(pair.split("=", 1) for pair in arg.split(",") if "=" in pair)

        # Detect old format: single pair like "projname=/path/to/dir"
        known_keys = {"name", "path", "url"}
        if (
            len(pairs) == 1
            and not pairs.keys() & known_keys
            and (
                "/" in next(iter(pairs.values())) or "\\" in next(iter(pairs.values()))
            )
        ):
            stdlogger.warning(
                "Skipping reference project '%s': appears to be old format. "
                "Use: name=<name>,path=<path>[,url=<url>]",
                arg,
            )
            continue

        # Validate "name" is present
        name = pairs.get("name")
        if not name:
            stdlogger.warning(
                "Invalid reference project format (missing 'name' key): argument=%s",
                arg,
            )
            continue

        # Validate "path" is present
        path_str = pairs.get("path")
        if not path_str:
            stdlogger.warning(
                "Invalid reference project format (missing 'path' key): argument=%s",
                arg,
            )
            continue

        # Convert to canonical resolved path
        project_path = Path(path_str).resolve()

        explicit_url = pairs.get("url")

        # Check path existence — relaxed when URL is provided
        if not project_path.exists() and explicit_url is None:
            stdlogger.warning(
                "Reference project path does not exist: name=%s, path=%s",
                name,
                project_path,
            )
            continue

        if project_path.exists() and not project_path.is_dir():
            stdlogger.warning(
                "Reference project path is not a directory: name=%s, path=%s",
                name,
                project_path,
            )
            continue

        # Check for overlap with the main project directory
        if project_path.exists():
            if project_path == resolved_project_dir:
                stdlogger.warning(
                    "Reference project '%s' points to the same directory as the main project, ignoring: path=%s",
                    name,
                    project_path,
                )
                continue
            elif project_path.is_relative_to(resolved_project_dir):
                stdlogger.warning(
                    "Reference project '%s' is a subdirectory of the main project, ignoring: path=%s",
                    name,
                    project_path,
                )
                continue
            elif resolved_project_dir.is_relative_to(project_path):
                stdlogger.warning(
                    "Reference project '%s' is a parent of the main project, ignoring: path=%s",
                    name,
                    project_path,
                )
                continue

        # Detect and verify URL (raises ValueError on mismatch)
        url = detect_and_verify_url(project_path, explicit_url, name)

        # Handle duplicate names with auto-rename
        final_name = name
        counter = 2
        while final_name in validated_projects:
            final_name = f"{name}_{counter}"
            counter += 1

        validated_projects[final_name] = ReferenceProject(
            name=final_name, path=project_path, url=url
        )

    return validated_projects


def _main() -> None:
    """Parse arguments, configure logging, and start the server.

    Raises:
        ValueError: On any CLI parse error or startup validation failure.
        OSError: If the fallback logging bootstrap fails after an invalid
            --log-level (e.g. an unwritable log directory).
    """
    argv = sys.argv[1:]
    if any(token in _HELP_TOKENS for token in argv):
        # -h/--help/--version are handled by argparse's own action, which
        # exits the process directly (SystemExit) — nothing below ever runs.
        parse_args(argv)
        return

    set_traffic_log_context(command="mcp-workspace server")

    pre = _pre_parse(argv)
    project_dir = _resolve_project_dir(pre.project_dir)
    log_file = _resolve_log_file(pre, project_dir)

    if log_file is not None or pre.console_only:
        try:
            log_level = _validate_log_level(pre.log_level)
        except ValueError as log_level_error:
            # Bootstrap a sink with a known-good level so the bad value still
            # lands in a real log file instead of triggering the fallback. If
            # the bootstrap itself fails (e.g. an unwritable log directory),
            # chain the two errors so neither is lost.
            try:
                setup_logging("INFO", log_file)
            except OSError as os_error:
                raise OSError(
                    f"{os_error}; additionally, invalid --log-level: {log_level_error}"
                ) from log_level_error
            raise log_level_error
        setup_logging(log_level, log_file)

    stdlogger.debug("Logger initialized in main")

    if project_dir is None:
        raise ValueError(
            f"--project-dir is required and must be an existing directory: {pre.project_dir!r}"
        )

    args, unknown = parse_args(argv)

    for token in unknown:
        stdlogger.warning("Ignoring unknown startup argument: %s", token)
    stdlogger.info(
        "Starting mcp-workspace %s: python=%s project_dir=%s ignored_args=%s",
        __version__,
        sys.executable,
        project_dir,
        unknown,
    )

    # Validate file size limit (must be a positive integer when provided)
    if args.file_size_limit is not None and args.file_size_limit <= 0:
        raise ValueError(
            f"--file-size-limit must be a positive integer: {args.file_size_limit}"
        )

    # Activate the OS trust store BEFORE any TLS handshake can occur. This is a
    # hard guarantee owned by the entry point (not left to client call sites):
    # it covers PyGithub AND the raw `requests` download path in
    # github_operations. ensure_truststore() is idempotent and cheap; the
    # heavy startup cost (PyGithub/GitPython, ~530 modules) is what is deferred
    # via lazy imports, not this.
    ensure_truststore()

    # Parse reference projects
    reference_projects: Dict[str, ReferenceProject] = {}
    if args.reference_project:
        reference_projects = validate_reference_projects(
            args.reference_project, project_dir
        )

    # Import here to avoid circular imports (after logging is configured)
    from mcp_workspace.server import run_server

    stdlogger.debug(
        "Starting MCP server: project_dir=%s, log_level=%s, log_file=%s",
        project_dir,
        args.log_level,
        log_file,
    )

    # Run the server with the project directory and reference projects
    run_server(
        project_dir,
        reference_projects=reference_projects,
        file_size_limit=args.file_size_limit,
        fail_on_reviews=args.fail_on_reviews,
        enforce_base_branch_format=args.enforce_base_branch_format,
    )


def main() -> None:
    """Main entry point for the MCP server."""
    try:
        _main()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _handle_startup_failure(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
