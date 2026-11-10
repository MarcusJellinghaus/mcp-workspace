"""Reference project lookups for the legacy GitHub tools in server.py."""

import logging

from mcp_coder_utils.log_utils import log_function_call

from mcp_workspace.reference_projects import ReferenceProject

logger = logging.getLogger(__name__)

_reference_projects: dict[str, ReferenceProject] = {}


@log_function_call
def set_reference_projects(reference_projects: dict[str, ReferenceProject]) -> None:
    """Set the reference projects for file operations.

    Args:
        reference_projects: Dictionary mapping project names to ReferenceProject instances
    """
    global _reference_projects  # pylint: disable=global-statement
    _reference_projects = (
        reference_projects.copy()
    )  # Create a copy to avoid external modifications

    # Log each reference project
    for project_name, project in reference_projects.items():
        logger.info("Reference project '%s' set to: %s", project_name, project.path)


def get_reference_repo_url(name: str) -> str:
    """Resolve a reference project name to its configured repository URL.

    Synchronous and side-effect free: it never clones.

    Returns:
        The configured repository URL.

    Raises:
        ValueError: If no reference project with the given name exists, or
            the project has no URL configured.
    """
    if name not in _reference_projects:
        raise ValueError(f"Reference project '{name}' not found")
    url = _reference_projects[name].url
    if url is None:
        raise ValueError(f"Reference project '{name}' has no URL configured")
    return url
