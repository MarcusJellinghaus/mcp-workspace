"""GitHub operations module for MCP Workspace.

This module provides GitHub API integration functionality for managing
pull requests, labels, and repository operations.
"""

from mcp_workspace.utils.repo_identifier import RepoIdentifier

from .base_manager import (
    BaseGitHubManager,
    IssueIdentityMismatchError,
    get_authenticated_username,
)
from .ci_results_manager import CIResultsManager, CIStatusData
from .labels_manager import LabelData, LabelsManager
from .pr_manager import MergeResult, PullRequestData, PullRequestManager
from .verification import CheckResult, verify_github

# Issue-related imports REMOVED per Decision #1
# Consumers must import from: mcp_workspace.github_operations.issues


__all__ = [
    "BaseGitHubManager",
    "CheckResult",
    "CIResultsManager",
    "CIStatusData",
    "IssueIdentityMismatchError",
    "LabelData",
    "LabelsManager",
    "MergeResult",
    "PullRequestData",
    "PullRequestManager",
    "RepoIdentifier",
    "get_authenticated_username",
    "verify_github",
]
