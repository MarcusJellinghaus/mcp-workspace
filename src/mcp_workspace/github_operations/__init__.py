"""GitHub operations module for MCP Workspace.

This module provides GitHub API integration functionality for managing
pull requests, labels, and repository operations.
"""

from mcp_workspace.config import get_trusted_commenters
from mcp_workspace.utils.repo_identifier import RepoIdentifier

from ._diagnostics import RetryError, format_rate_limit_error
from ._security_probes import verify_github_security
from .base_manager import (
    BaseGitHubManager,
    GithubException,
    IssueIdentityMismatchError,
    clear_login_cache,
    get_authenticated_username,
)
from .ci_results_manager import CIResultsManager, CIStatusData
from .labels_manager import LabelData, LabelsManager
from .pr_manager import PullRequestManager
from .pr_types import MergeResult, PullRequestData
from .trust import is_trusted_author
from .verification import CheckResult, verify_github

# GithubException, RetryError and format_rate_limit_error are re-exported so
# callers outside this package can catch and describe PyGithub/requests errors
# without importing PyGithub or requests themselves (see .importlinter).

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
    "RetryError",
    "clear_login_cache",
    "format_rate_limit_error",
    "get_authenticated_username",
    "get_trusted_commenters",
    "is_trusted_author",
    "verify_github",
    "verify_github_security",
]
