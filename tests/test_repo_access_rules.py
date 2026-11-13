"""Guard tests for this repository's own .mcp-file-access rules."""

from pathlib import Path

from mcp_workspace.file_tools.directory_utils import is_path_gitignored
from mcp_workspace.file_tools.file_access import (
    FileAccess,
    get_file_access,
    validate_access_rules,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_rules_file_is_valid() -> None:
    """The repository's rules file parses without problems."""
    assert validate_access_rules(REPO_ROOT) == []


def test_scratch_is_read_write() -> None:
    """The scratch area is writable through the MCP file tools."""
    assert get_file_access(".scratch/probe.py", REPO_ROOT) is FileAccess.READ_WRITE


def test_mcp_config_files_are_read_only() -> None:
    """MCP configuration and the rules file cannot be changed by the tools."""
    assert get_file_access(".mcp.json", REPO_ROOT) is FileAccess.READ_ONLY
    assert get_file_access(".mcp-file-access", REPO_ROOT) is FileAccess.READ_ONLY


def test_scratch_is_never_committed() -> None:
    """The scratch area is gitignored."""
    assert is_path_gitignored(".scratch/probe.py", REPO_ROOT) is True
