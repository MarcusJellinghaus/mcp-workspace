"""Git operations package - modular git utilities."""

from mcp_workspace.git_operations.base_branch import (
    BaseBranchSource,
    detect_base_branch_with_source,
)
from mcp_workspace.git_operations.branch_queries import (
    branch_exists,
    extract_issue_number_from_branch,
    get_current_branch_name,
    get_default_branch_name,
    has_remote_tracking_branch,
    validate_branch_name,
)
from mcp_workspace.git_operations.branches import (
    checkout_branch,
    create_branch,
    delete_branch,
)
from mcp_workspace.git_operations.commits import (
    commit_paths,
    commit_staged_files,
    get_head_commit_info,
    get_latest_commit_sha,
)
from mcp_workspace.git_operations.compact_diffs import get_compact_diff
from mcp_workspace.git_operations.core import (
    BranchProbe,
    CommitResult,
    GitResult,
    RebaseProbe,
    RebaseResult,
    RemoteBranchesResult,
    StatusResult,
    safe_repo_context,
)
from mcp_workspace.git_operations.diffs import (
    get_branch_diff,
    get_git_diff_for_commit,
)
from mcp_workspace.git_operations.file_tracking import (
    git_move,
    is_file_tracked,
)
from mcp_workspace.git_operations.parent_branch_detection import (
    MERGE_BASE_DISTANCE_THRESHOLD,
    detect_parent_branch_via_merge_base,
)
from mcp_workspace.git_operations.rebase import (
    is_rebase_in_progress,
    probe_rebase_conflicts,
    rebase_abort,
    rebase_continue,
    rebase_skip,
    rebase_start,
    reset_hard,
)
from mcp_workspace.git_operations.remotes import (
    clone_repo,
    fetch_remote,
    get_remote_url,
    get_repository_identifier,
    git_push,
    list_remote_branches,
    probe_origin_branch,
    pull,
    push_branch,
    rebase_onto_branch,
)
from mcp_workspace.git_operations.repository_status import (
    get_full_status,
    get_working_tree_status,
    is_git_repository,
    is_working_directory_clean,
)
from mcp_workspace.git_operations.staging import stage_all_changes, unstage_paths
from mcp_workspace.git_operations.verification import CheckResult, verify_git
from mcp_workspace.git_operations.workflows import (
    commit_all_changes,
    needs_rebase,
)

__all__ = [
    "BaseBranchSource",
    "BranchProbe",
    "CheckResult",
    "CommitResult",
    "GitResult",
    "MERGE_BASE_DISTANCE_THRESHOLD",
    "RebaseProbe",
    "RebaseResult",
    "RemoteBranchesResult",
    "StatusResult",
    "branch_exists",
    "checkout_branch",
    "clone_repo",
    "commit_all_changes",
    "commit_paths",
    "commit_staged_files",
    "create_branch",
    "delete_branch",
    "detect_base_branch_with_source",
    "detect_parent_branch_via_merge_base",
    "extract_issue_number_from_branch",
    "fetch_remote",
    "get_branch_diff",
    "get_compact_diff",
    "get_current_branch_name",
    "get_default_branch_name",
    "get_full_status",
    "get_git_diff_for_commit",
    "get_head_commit_info",
    "get_latest_commit_sha",
    "get_remote_url",
    "get_repository_identifier",
    "get_working_tree_status",
    "git_move",
    "git_push",
    "has_remote_tracking_branch",
    "is_file_tracked",
    "is_git_repository",
    "is_rebase_in_progress",
    "is_working_directory_clean",
    "list_remote_branches",
    "needs_rebase",
    "probe_origin_branch",
    "probe_rebase_conflicts",
    "pull",
    "push_branch",
    "rebase_abort",
    "rebase_continue",
    "rebase_onto_branch",
    "rebase_skip",
    "rebase_start",
    "reset_hard",
    "safe_repo_context",
    "stage_all_changes",
    "unstage_paths",
    "validate_branch_name",
    "verify_git",
]
