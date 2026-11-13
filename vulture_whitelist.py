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
# Reference Projects
# =============================================================================
_.clear_clone_failure_cache

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

# Module-level name pytest reads during collection to apply marks to every test
# in the module. Never referenced by our own code.
_.pytestmark

# =============================================================================
# Git Operations Public API
# =============================================================================
# Exported for downstream consumers (mcp_coder issue ③).
# These functions/classes are not called within mcp_workspace itself.

_.has_remote_tracking_branch
_.delete_branch
_.PushResult
_.push_branch

# Gitignore-only check kept as public API alongside the .mcp-file-access checks
# (issue #83); the tools call require_access instead.
_.check_path_not_gitignored

# PEP 562 module __getattr__ in directory_utils, re-exporting the file_access
# API lazily; Python calls it on attribute lookup, never our own code.
_.__getattr__

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
# JobData TypedDict fields - accessed via .get() in ci_log_parser (issue #382)
_.run_html_url
_.run_event

# PRFeedback TypedDict fields - accessed via subscript, vulture can't see usage
_.resolved_thread_count
# MergeResult TypedDict field - accessed via subscript
_.outcome
# CommitResult TypedDict field - accessed via subscript
_.error_category
# StatusResult TypedDict field - accessed via subscript
_.clean
# RebaseProbe TypedDict field - accessed via subscript
_.files
# BranchProbe TypedDict field - accessed via subscript
_.exists
# RemoteBranchesResult TypedDict field - accessed via subscript
_.branches
# ConflictBlobInfoResult / ConflictBlobEntry / ConflictStageResult TypedDict fields
_.entries
_.stages
_.is_binary
_.content
# TreeEntry TypedDict fields - accessed via subscript
_.mode
_.type
_.sha
_.path
# CacheData TypedDict field - accessed via subscript
_.cached_at
# CIStatusData TypedDict field - accessed via subscript
_.lookup_failed
# OpenPullRequest TypedDict field - accessed via subscript / .get()
_.head_label

# Test fixtures
_.mock_zip_content
_.sample_issue
_._patch_get_default_branch
_._reset_activated_flag
# Autouse fixtures for network diagnostics (referenced by pytest collection only)
_.reset_network_diagnostics_guard
_._default_network_ok
# Autouse fixture resetting the server's @me login cache (pytest collection only)
_.reset_login_cache
# Autouse fixtures for issue #236 review-gate tests (referenced by pytest collection only)
_._github_token
# Autouse fixture restoring root logger state in test_startup.py (pytest collection only)
_._snapshot_logging
# Fixtures for issue #321 base-branch tests, reached through their name= alias
_._status_mocks  # name="status_mocks"
_._report  # name="report"
_.fixture_manager  # name="manager"
_.fixture_current  # name="current"
# Autouse fixtures for issue #321 base-branch tests (referenced by pytest collection only)
_._reset_malformed_base_branch_warnings
_.origin_has_base
# Fixture for issue #338 unstable re-check tests, reached through its name= alias
_.fixture_env  # name="env"
# Autouse fixture isolating tests from the real trusted-commenters allowlist (issue #336, pytest collection only)
_._empty_trusted_commenters
# Autouse fixture isolating tests from the real [github] enterprise_hosts list
_._empty_enterprise_hosts
# Fixture reached through pytest.mark.usefixtures("allow_test_ghes_hosts")
_.allow_test_ghes_hosts
# Fixtures for issue #342 untrusted base-branch tests, reached through their name= alias
_._editor  # name="editor"
_._token_login  # name="token_login"
# Fixture for issue #352 base-branch source tests, reached through its name= alias
_._git_mocks  # name="git_mocks"
# Fixture for issue #374 PullRequestCache alerts-slot tests, reached through its name= alias
_._fetch  # name="fetch"
# Autouse fixture defaulting fetch_rules to no rulesets (issue #350, pytest collection only)
_._default_rules_empty
# Autouse fixture clearing the per-process repository cache (issue #360, pytest collection only)
_._reset_repository_cache
# Autouse fixture turning the traffic log off for tests (issue #359, pytest collection only)
_._traffic_log_off
# Autouse fixture in TestGetTrafficLogDir (issue #359, pytest collection only)
_._clear_cache
# Autouse fixture keeping tests from reading the real read_max_lines config (issue #380, pytest collection only)
_._no_read_max_lines
# Named fixtures in issues/test_status.py (issue #388, pytest collection only)
_._cache_write  # name="cache_write"
_._cached_labels  # name="cached_labels"
# Fixture for issue #220 find_merged_pr_by_head_sha tests, reached through its name= alias
_.fixture_mock_repo  # name="mock_repo"
# BaseHTTPRequestHandler overrides in the local test HTTP server (issue #359, called by http.server)
_.do_GET
_.log_message
# Parameter kept only to match PyGithub's Requester signature in the fake stand-ins (issue #359)
_.stream
