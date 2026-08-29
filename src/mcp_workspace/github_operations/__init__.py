"""GitHub operations module for MCP Workspace.

This module provides GitHub API integration functionality for managing
pull requests, labels, and repository operations.
"""

from mcp_workspace.utils.repo_identifier import RepoIdentifier

# GithubException is re-exported so callers outside this package can catch
# PyGithub errors without importing PyGithub themselves (see .importlinter).
from .base_manager import (
    BaseGitHubManager,
    GithubException,
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
    "GithubException",
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
