"""Tests for server_reference_tools.set_reference_projects."""

from pathlib import Path
from unittest.mock import patch

import mcp_workspace.server_reference_tools as ref_tools_module
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.server_reference_tools import set_reference_projects


def _make_projects() -> dict[str, ReferenceProject]:
    return {
        "proj1": ReferenceProject(name="proj1", path=Path("/path/to/proj1").resolve()),
        "proj2": ReferenceProject(name="proj2", path=Path("/path/to/proj2").resolve()),
    }


class TestSetReferenceProjects:
    """Test server storage and initialization of reference projects."""

    def test_set_reference_projects(self) -> None:
        """Test setting reference projects storage."""
        test_projects = _make_projects()

        set_reference_projects(test_projects)

        # Check that the global variable was updated
        assert ref_tools_module._reference_projects == test_projects

    def test_reference_projects_logging(self) -> None:
        """Test INFO level logging during initialization."""
        test_projects = _make_projects()

        with patch("mcp_workspace.server_reference_tools.logger") as mock_logger:
            set_reference_projects(test_projects)

            # Verify INFO level logging was called
            assert mock_logger.info.called

            # Check that project details were logged
            info_calls = mock_logger.info.call_args_list
            assert len(info_calls) >= 1
