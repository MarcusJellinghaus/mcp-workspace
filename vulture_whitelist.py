"""
Vulture Whitelist - Intentionally Unused Code
==============================================
This file contains code patterns that vulture should not flag as unused.

Use this for:
- Public API methods that external users call
- Protocol-required methods (MCP server handlers)
- Callback functions registered dynamically
- __all__ exports that are imported elsewhere

Run: vulture src tests vulture_whitelist.py --min-confidence 60
"""

# =============================================================================
# MCP Server Tool Handlers
# =============================================================================
# These are registered dynamically by the MCP framework and called by clients.
# They appear unused but are part of the public MCP tool API.

# File operation tools registered in server.py
_.list_directory
_.read_file
_.save_file
_.append_file
_.delete_this_file
_.move_file
_.edit_file

_.search_files

# Reference project tools
_.get_reference_projects
_.list_reference_directory
_.read_reference_file
_.search_reference_files
_.clear_clone_failure_cache

# Git read-only operation tool registered in server.py
_.git

# GitHub read-only tools registered in server.py
_.github_issue_view
_.github_issue_list
_.github_pr_view
_.github_search

# Base branch detection tool
_.get_base_branch

# File size check tool
_.check_file_size

# Branch status check tool
_.check_branch_status

# =============================================================================
# Public API Exports
# =============================================================================
# Exported in __init__.py for external use

# Version information
_.__version__

# =============================================================================
# Test Fixtures and Utilities
# =============================================================================
# Pytest fixtures defined in conftest.py

_.temp_dir
_.temp_git_repo
_.sample_file
_.setup_and_cleanup
_.setup_test_file
_.setup_server

# =============================================================================
# Git Operations Public API
# =============================================================================
# Exported for downstream consumers (mcp_coder issue ③).
# These functions/classes are not called within mcp_workspace itself.

_.has_remote_tracking_branch
_.delete_branch
_.PushResult
_.push_branch

# =============================================================================
# Test Mock Attributes
# =============================================================================
# Mock protocol methods used in test_parent_branch_detection.py

_.__iter__
_.__enter__
_.__exit__
_.__getitem__

# =============================================================================
# Protocol-Required Attributes
# =============================================================================
# Attributes required by MCP protocol but may not be referenced in our code

_.name
_.description
_.inputSchema

# =============================================================================
# GitHub Operations
# =============================================================================
# Enum members used by external callers or for completeness
_.CLOSED
_.REOPENED
_.ASSIGNED
_.UNASSIGNED
_.MILESTONED
_.DEMILESTONED
_.REFERENCED
_.CROSS_REFERENCED
_.COMMENTED
_.MENTIONED
_.SUBSCRIBED
_.UNSUBSCRIBED
_.RENAMED
_.LOCKED
_.UNLOCKED
_.REVIEW_REQUESTED
_.REVIEW_REQUEST_REMOVED
_.CONVERTED_TO_DRAFT
_.READY_FOR_REVIEW

# Verification API (verify_github)
_.verify_github
_.CheckResult
_.ok
_.severity
_.install_hint
_.token_fingerprint

# CI results manager - variables used in dict unpacking / data extraction
_.run_ids
_.workflow_name
_.workflow_path
_.commit_sha
_.jobs_fetch_warning
_.issues

# PRFeedback TypedDict fields - accessed via subscript, vulture can't see usage
_.resolved_thread_count
# CommitResult TypedDict field - accessed via subscript
_.error_category

# Test fixtures
_.mock_zip_content
_.sample_issue
_._patch_get_default_branch
_._reset_activated_flag
