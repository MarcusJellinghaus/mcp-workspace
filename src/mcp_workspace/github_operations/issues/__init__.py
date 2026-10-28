"""Issues package for GitHub issue operations.

This package provides:
- IssueManager: Main class for issue CRUD operations
- IssueBranchManager: Branch-issue linking via GraphQL
- Type definitions: IssueData, CommentData, EventData, IssueEventType
- Cache functions: get_all_cached_issues, update_issue_labels_in_cache
- Utilities: generate_branch_name_from_issue, BranchCreationResult, CacheData
"""

# Cache functions and types
from ._cache_io import (
    CacheData,
    _get_cache_file_path,
    _load_cache_file,
    _save_cache_file,
    get_issue_cache_last_checked,
)

# Base utilities
from .base import MalformedBaseBranchError, parse_base_branch

# Branch manager and utilities
from .branch_manager import BranchLookup, BranchLookupError, IssueBranchManager
from .branch_naming import BranchCreationResult, generate_branch_name_from_issue
from .cache import (
    _log_stale_cache_entries,
    get_all_cached_issues,
    update_issue_labels_in_cache,
)
from .linked_branches_mixin import ClosingPRRef

# Main managers
from .manager import IssueManager

# Types (Note: LabelData not included - use labels_manager instead)
from .types import (
    CommentData,
    EventData,
    IssueData,
    IssueEventType,
    create_empty_issue_data,
)

__all__ = [
    # Types (LabelData excluded - use labels_manager)
    "IssueEventType",
    "IssueData",
    "CommentData",
    "EventData",
    "create_empty_issue_data",
    # Main manager
    "IssueManager",
    # Branch manager
    "IssueBranchManager",
    "BranchLookup",
    "BranchLookupError",
    "BranchCreationResult",
    "generate_branch_name_from_issue",
    "ClosingPRRef",
    # Cache
    "CacheData",
    "get_all_cached_issues",
    "get_issue_cache_last_checked",
    "update_issue_labels_in_cache",
    # Utility functions (exported for testing)
    "parse_base_branch",
    "MalformedBaseBranchError",
    # Private cache functions (exported for testing)
    "_get_cache_file_path",
    "_load_cache_file",
    "_log_stale_cache_entries",
    "_save_cache_file",
]
