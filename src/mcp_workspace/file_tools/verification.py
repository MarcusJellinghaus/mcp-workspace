"""Check a project's .mcp-file-access rules file."""

from __future__ import annotations  # CheckResult exists only for type checking

from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from mcp_workspace.file_tools.access_rules import ACCESS_RULES_FILE, load_access_rules

if TYPE_CHECKING:
    from mcp_workspace.git_operations import CheckResult


class FileAccessVerification(TypedDict):
    """Result of verify_file_access."""

    rules_file: CheckResult
    overall_ok: bool


def verify_file_access(project_dir: Path) -> FileAccessVerification:
    """Check the project's rules file, in the shape verify_git uses.

    Loading the file logs each problem once, so calling this at startup
    surfaces an invalid rules file in the server log.

    Args:
        project_dir: Project root directory.

    Returns:
        The ``rules_file`` row and ``overall_ok``, which is False only when
        the rules file is invalid.
    """
    rules = load_access_rules(project_dir)
    row: CheckResult
    if rules.problems:
        row = {
            "ok": False,
            "value": "invalid",
            "severity": "error",
            "error": "; ".join(rules.problems),
        }
    elif not (project_dir / ACCESS_RULES_FILE).exists():
        row = {"ok": True, "value": "absent - gitignore only", "severity": "error"}
    else:
        row = {"ok": True, "value": f"{len(rules.rules)} rules", "severity": "error"}
    return {"rules_file": row, "overall_ok": row["ok"] is True}
