"""Main entry point for the MCP server."""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Import logging utilities
from mcp_coder_utils.log_utils import setup_logging

from mcp_workspace import __version__
from mcp_workspace._ssl import ensure_truststore
from mcp_workspace.reference_projects import ReferenceProject, detect_and_verify_url

# Create loggers
stdlogger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="MCP File System Server - A Model Context Protocol server providing file operation tools"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"mcp-workspace {__version__}",
        help="Show version number and exit",
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        required=True,
        help="Base directory for all file operations (required)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level (default: INFO)",
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
    return parser.parse_args()


def validate_reference_projects(
    reference_args: List[str], project_dir: Path
) -> Dict[str, ReferenceProject]:
    """Parse and validate reference project arguments.

    Parses comma-separated KV pairs: name=proj,path=/dir,url=https://...
    Validates name and path are present. Logs warnings for invalid
    references and continues with valid ones only. Auto-renames duplicates.
    Filters out reference projects that overlap with project_dir.

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


def main() -> None:
    """
    Main entry point for the MCP server.
    """
    # Parse command line arguments
    args = parse_args()

    # Validate project directory first
    project_dir = Path(args.project_dir)
    if not project_dir.exists() or not project_dir.is_dir():
        print(
            f"Error: Project directory does not exist or is not a directory: {project_dir}"
        )
        sys.exit(1)

    # Convert to canonical resolved path
    project_dir = project_dir.resolve()

    # Validate file size limit (must be a positive integer when provided)
    if args.file_size_limit is not None and args.file_size_limit <= 0:
        print(
            f"Error: --file-size-limit must be a positive integer: {args.file_size_limit}"
        )
        sys.exit(1)

    # Generate default log file path if not specified
    if args.console_only:
        log_file = None
    elif args.log_file:
        log_file = args.log_file
    else:
        # Create default log file in project_dir/logs/ with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logs_dir = project_dir / "logs"
        log_file = str(logs_dir / f"mcp_workspace_{timestamp}.log")

    # Configure logging now that we have the project directory
    setup_logging(args.log_level, log_file)

    # Add debug logging after logger is initialized
    stdlogger.debug("Logger initialized in main")

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
        try:
            reference_projects = validate_reference_projects(
                args.reference_project, project_dir
            )
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

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
    )


if __name__ == "__main__":
    main()
