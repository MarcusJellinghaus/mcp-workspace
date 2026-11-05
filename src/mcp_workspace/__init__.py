"""MCP server providing workspace file operations."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mcp-workspace")
except PackageNotFoundError:
    # Package is not installed
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
