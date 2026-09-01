"""Tests for the server-level MCP instructions text."""

import re

from mcp_workspace.server import mcp


def test_server_instructions_describe_reference_projects() -> None:
    """Server instructions advertise reference projects without naming tools or paths."""
    text = mcp.instructions
    assert text is not None
    assert "reference project" in text.lower()
    # Only git() and get_reference_projects() may be named; no tool roster
    assert "github_" not in text
    assert "read_reference_file" not in text
    assert "search_reference_files" not in text
    assert "list_reference_directory" not in text
    # No filesystem path may reach the model. Match real path shapes only, so
    # legitimate slashes such as "owner/repo" or a URL still pass.
    assert not re.search(r"[A-Za-z]:[\\/]", text), "drive-letter path in instructions"
    assert "\\" not in text, "backslash path separator in instructions"
    assert not re.search(r"(?:\A|\s)~?/\S", text), "absolute POSIX path in instructions"
