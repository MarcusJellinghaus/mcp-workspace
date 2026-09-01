"""Tests for the server-level MCP instructions text."""

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
    # No filesystem path may reach the model
    assert "\\" not in text and "/" not in text
