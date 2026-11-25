"""``mcp-workspace verify``: print FILE ACCESS, GIT, GITHUB and GITHUB SECURITY.

Never imports ``mcp_workspace.main``: main imports this module lazily, so an
import back would form a cycle.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

from mcp_coder_utils.verify_render import STATUS_SYMBOLS, Row, SectionBuilder

from mcp_workspace._ssl import ensure_truststore
from mcp_workspace.cli.verify_formatting import (
    format_file_access_section,
    format_git_section,
    format_github_section,
    format_github_security_section,
)
from mcp_workspace.file_tools import verify_file_access
from mcp_workspace.git_operations import verify_git
from mcp_workspace.github_operations import github_security_rows, verify_github
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.traffic_log import set_traffic_log_context


def execute_verify(
    project_dir: Path,
    reference_projects: Mapping[str, ReferenceProject],
    rejected: Sequence[tuple[str, str]],
) -> int:
    """Run the checks, print the four sections and return the exit code.

    FILE ACCESS lists the workspace, then the accepted references in mapping
    order, then the rejected references. A reference whose path is missing is
    a warning only. GITHUB SECURITY never affects the exit code.

    Args:
        project_dir: Workspace directory.
        reference_projects: Accepted references keyed by their final name.
        rejected: ``(label, reason)`` pairs, already credential-scrubbed.

    Returns:
        0 when every FILE ACCESS row is ok and GIT and GITHUB report
        ``overall_ok``; 1 otherwise.
    """
    ensure_truststore()
    set_traffic_log_context(command="mcp-workspace verify")
    with SectionBuilder() as out:
        out.open("FILE ACCESS")
        workspace = verify_file_access(project_dir)
        files_ok = workspace["overall_ok"]
        out.add(
            *format_file_access_section(workspace, STATUS_SYMBOLS, label="workspace")
        )
        for name, ref in reference_projects.items():
            if not ref.path.exists():
                out.add(Row(name, STATUS_SYMBOLS["warning"], "path not found"))
                continue
            result = verify_file_access(ref.path)
            files_ok &= result["overall_ok"]
            out.add(*format_file_access_section(result, STATUS_SYMBOLS, label=name))
        for label, reason in rejected:
            out.add(Row(label, STATUS_SYMBOLS["failure"], f"rejected: {reason}"))
            files_ok = False

        git = verify_git(project_dir, actually_sign=True)
        out.section("GIT", format_git_section(git, STATUS_SYMBOLS))
        github = verify_github(project_dir)
        out.section("GITHUB", format_github_section(github, STATUS_SYMBOLS))
        out.section(
            "GITHUB SECURITY",
            format_github_security_section(
                github_security_rows(project_dir), STATUS_SYMBOLS
            ),
        )
    return 0 if files_ok and git.get("overall_ok") and github.get("overall_ok") else 1
